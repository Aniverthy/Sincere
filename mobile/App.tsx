import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { RootNavigator } from './src/navigation';

/**
 * App root.
 *
 * Screen map and client responsibilities: TECHNICAL_IMPLEMENTATION_PLAN.md §4.
 * Navigation is driven by the §6 lifecycle state machine — see `src/navigation/index.tsx`.
 */

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // §17: there are no push notifications in MVP, so the app discovers new activity by
      // being reopened. Refetching on foreground is what makes that feel current.
      refetchOnWindowFocus: true,
      retry: 2,
      staleTime: 30_000,
    },
  },
});

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <StatusBar style="light" />
          <RootNavigator />
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
