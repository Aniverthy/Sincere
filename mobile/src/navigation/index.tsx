import { NavigationContainer, type Theme as NavTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { useEffect } from 'react';
import { View } from 'react-native';

import { Loading } from '../components';
import { useSession } from '../state/session';
import { colors, typography } from '../theme';

// Feature entry points. Cross-feature imports go through these index files only, mirroring
// the backend's §3 rule that a module exposes exactly one public surface.
import { OnboardingFlow, RejectedScreen, VerifyingScreen } from '../features/identity';
import { WaitlistScreen } from '../features/admission';
import { HomeScreen, MatchesScreen } from '../features/matching';
import { ChatScreen } from '../features/chat';
import { MeScreen } from '../features/monetization';
import { WeMetPrompt } from '../features/feedback_ml';
import { WarningInterstitial } from '../features/antiabuse';

/**
 * Root navigator — a direct rendering of the §6 lifecycle state machine.
 *
 * The navigator switches on the token's `scope` claim rather than pushing screens, so a user
 * in one lifecycle state has **no mounted route** into another state's screens. §5 enforces
 * the same rule server-side ("a waitlisted man's token cannot call matching/chat endpoints");
 * this makes the client structurally agree instead of merely hiding buttons.
 *
 * That is why nothing in the waitlist flow navigates to Home. The user gets there by being
 * *admitted*: the server re-issues a token with `scope: active`, the session store updates,
 * and this switch re-renders into a different tree.
 */

export type RootStackParamList = {
  Waitlist: undefined;
  Main: undefined;
  Chat: { matchId: string; displayName: string };
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tabs = createBottomTabNavigator();

const navTheme: NavTheme = {
  dark: true,
  colors: {
    primary: colors.primary,
    background: colors.background,
    card: colors.surface,
    text: colors.text,
    border: colors.border,
    notification: colors.danger,
  },
  fonts: {
    regular: { fontFamily: 'System', fontWeight: '400' },
    medium: { fontFamily: 'System', fontWeight: '500' },
    bold: { fontFamily: 'System', fontWeight: '700' },
    heavy: { fontFamily: 'System', fontWeight: '800' },
  },
};

const screenOptions = {
  headerStyle: { backgroundColor: colors.background },
  headerTitleStyle: { ...typography.heading, color: colors.text },
  headerTintColor: colors.text,
  contentStyle: { backgroundColor: colors.background },
} as const;

/** The active-user surface. Mounted only for `scope: active`. */
function MainTabs() {
  return (
    <Tabs.Navigator
      screenOptions={{
        ...screenOptions,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textFaint,
      }}
    >
      <Tabs.Screen name="Today" component={HomeScreen} options={{ title: 'Today' }} />
      <Tabs.Screen name="Matches" component={MatchesScreen} options={{ title: 'Matches' }} />
      <Tabs.Screen name="Me" component={MeScreen} options={{ title: 'Me' }} />
    </Tabs.Navigator>
  );
}

/**
 * Modals that can interrupt any active-user screen.
 *
 * Both render `null` until the server says there is something to show, so they cost nothing
 * when idle. They live above the navigator because §4 requires the warning interstitial to be
 * unmissable — a screen-level placement could be navigated away from.
 */
function ActiveOverlays() {
  return (
    <>
      <WarningInterstitial />
      <WeMetPrompt />
    </>
  );
}

export function RootNavigator() {
  const { status, scope, restore } = useSession();

  useEffect(() => {
    void restore();
  }, [restore]);

  if (status === 'loading') {
    return <Loading label="Sincère" />;
  }

  // Signed out, or mid-onboarding: the linear signup sequence, outside the navigator.
  // §5 gives onboarding tokens a scope that unlocks only verification routes, so there is
  // nothing else to navigate to.
  if (status === 'signed_out' || scope === 'onboarding') {
    return <OnboardingFlow />;
  }

  if (scope === 'pending_review') {
    return <VerifyingScreen />;
  }

  return (
    <NavigationContainer theme={navTheme}>
      <Stack.Navigator screenOptions={screenOptions}>
        {scope === 'waitlisted' ? (
          // FR-2.6: the waitlist is a one-way door — never evicted back here, and no route
          // out of it except admission. Matching and chat are simply not in this tree.
          <Stack.Screen
            name="Waitlist"
            component={WaitlistScreen}
            options={{ title: 'Your place in line' }}
          />
        ) : scope === 'active' ? (
          <>
            <Stack.Screen name="Main" component={MainTabs} options={{ headerShown: false }} />
            <Stack.Screen
              name="Chat"
              component={ChatScreen}
              options={({ route }) => ({ title: route.params.displayName })}
            />
          </>
        ) : (
          <Stack.Screen
            name="Main"
            component={RejectedScreen}
            options={{ headerShown: false }}
          />
        )}
      </Stack.Navigator>

      {scope === 'active' ? (
        <View style={{ position: 'absolute' }}>
          <ActiveOverlays />
        </View>
      ) : null}
    </NavigationContainer>
  );
}
