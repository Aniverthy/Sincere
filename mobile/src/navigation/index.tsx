import { NavigationContainer, type Theme as NavTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator, type BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { useEffect } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { GlassSurface, Loading, Logo } from '../components';
import { useSession } from '../state/session';
import { colors, radius, spacing, typography } from '../theme';

import { OnboardingFlow, RejectedScreen, VerifyingScreen } from '../features/identity';
import { WaitlistScreen } from '../features/admission';
import { HomeScreen, MatchesScreen } from '../features/matching';
import { ChatScreen } from '../features/chat';
import { MeScreen } from '../features/monetization';
import { WeMetPrompt } from '../features/feedback_ml';
import { WarningInterstitial } from '../features/antiabuse';

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
    primary: colors.rose[500],
    background: colors.bg.wine,
    card: colors.glass.raised.fill,
    text: colors.text.primary,
    border: colors.glass.ambient.border,
    notification: colors.dangerRed,
  },
  fonts: {
    regular: { fontFamily: 'Manrope_400Regular', fontWeight: '400' },
    medium: { fontFamily: 'Manrope_500Medium', fontWeight: '500' },
    bold: { fontFamily: 'Manrope_700Bold', fontWeight: '700' },
    heavy: { fontFamily: 'Fraunces_600SemiBold', fontWeight: '800' },
  },
};

/** Floating Liquid Glass Tab Bar */
function CustomFloatingTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.tabBarContainer, { bottom: Math.max(insets.bottom, spacing.md) }]}>
      <GlassSurface tier="floating" radius={radius.pill} sheen style={styles.tabBarGlass}>
        <View style={styles.tabBarInner}>
          {state.routes.map((route, index) => {
            const { options } = descriptors[route.key];
            const label = options.title ?? route.name;
            const isFocused = state.index === index;

            const onPress = () => {
              const event = navigation.emit({
                type: 'tabPress',
                target: route.key,
                canPreventDefault: true,
              });

              if (!isFocused && !event.defaultPrevented) {
                navigation.navigate(route.name);
              }
            };

            return (
              <Pressable
                key={route.key}
                onPress={onPress}
                style={styles.tabItem}
                accessibilityRole="button"
                accessibilityState={{ selected: isFocused }}
              >
                {/* Active Tab Glow */}
                {isFocused && <View style={styles.activeGlow} />}
                <Text
                  style={[
                    styles.tabLabel,
                    isFocused ? styles.tabLabelActive : styles.tabLabelInactive,
                  ]}
                >
                  {label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </GlassSurface>
    </View>
  );
}

/** Active user surface with floating glass tab bar. */
function MainTabs() {
  return (
    <Tabs.Navigator
      tabBar={(props) => <CustomFloatingTabBar {...props} />}
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.bg.wine },
      }}
    >
      <Tabs.Screen name="Today" component={HomeScreen} options={{ title: 'Today' }} />
      <Tabs.Screen name="Matches" component={MatchesScreen} options={{ title: 'Matches' }} />
      <Tabs.Screen name="Me" component={MeScreen} options={{ title: 'Me' }} />
    </Tabs.Navigator>
  );
}

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

  if (status === 'signed_out' || scope === 'onboarding') {
    return <OnboardingFlow />;
  }

  if (scope === 'pending_review') {
    return <VerifyingScreen />;
  }

  return (
    <NavigationContainer theme={navTheme}>
      <Stack.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: colors.bg.wine },
          headerTitleStyle: { ...typography.displayM, color: colors.text.primary },
          headerTintColor: colors.text.primary,
          contentStyle: { backgroundColor: colors.bg.wine },
        }}
      >
        {scope === 'waitlisted' ? (
          <Stack.Screen
            name="Waitlist"
            component={WaitlistScreen}
            options={{
              title: 'Your place in line',
              headerTitle: () => (
                <View style={styles.headerTitleRow}>
                  <Logo size={32} />
                  <Text style={styles.headerTitleText}>Your place in line</Text>
                </View>
              ),
            }}
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

const styles = StyleSheet.create({
  tabBarContainer: {
    position: 'absolute',
    left: spacing.lg,
    right: spacing.lg,
    alignItems: 'center',
  },
  tabBarGlass: {
    width: '100%',
    maxWidth: 360,
  },
  tabBarInner: {
    flexDirection: 'row',
    height: 58,
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingHorizontal: spacing.sm,
  },
  tabItem: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    position: 'relative',
  },
  activeGlow: {
    position: 'absolute',
    width: 48,
    height: 32,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(207, 65, 115, 0.25)',
  },
  tabLabel: {
    ...typography.label,
  },
  tabLabelActive: {
    color: colors.warmBeige,
    fontFamily: 'Manrope_700Bold',
  },
  tabLabelInactive: {
    color: 'rgba(246, 216, 189, 0.55)',
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  headerTitleText: {
    ...typography.displayM,
    color: colors.text.primary,
  },
});
