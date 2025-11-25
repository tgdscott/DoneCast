// PostHog frontend initialization
import posthog from 'posthog-js';

const env = import.meta.env;

if (env.VITE_POSTHOG_KEY) {
  posthog.init(env.VITE_POSTHOG_KEY, {
    api_host: env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com',
    person_profiles: 'identified_only', // or 'always' to create profiles for anonymous users as well
    loaded: (posthog) => {
      if (env.DEV) posthog.debug(); // debug mode in development
    },
  });
}
