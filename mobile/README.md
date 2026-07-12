# Sincere mobile app (React Native)

Structural scaffold only - run the React Native toolchain init (e.g. `npx react-native init`
or Expo) before development starts, then merge this structure into it.

- `src/screens/` - one file per screen; map in TECHNICAL_IMPLEMENTATION_PLAN.md section 4
- `src/api/` - REST + WebSocket clients (API surface: TECHNICAL_IMPLEMENTATION_PLAN.md section 7)
- `src/navigation/` - stack/tab navigators
- `src/state/` - app state stores
- `src/components/`, `src/hooks/`, `src/theme/`, `src/utils/` - the usual suspects

Product rules the client owns (see docs): location captured once per app-open (no background
tracking), dwell-time measurement on swipes, mandatory "Boosted" label rendering, no push
notifications in MVP.
