const isDesktopExport =
  process.env.npm_lifecycle_event === "build:desktop" ||
  process.env.VIBE_LEARNER_DESKTOP_EXPORT === "1";

/** @type {import('next').NextConfig} */
const nextConfig = {
  typedRoutes: true,
  env: {
    NEXT_PUBLIC_TAVERN_ROOM_PROFILING:
      process.env.NEXT_PUBLIC_TAVERN_ROOM_PROFILING === "1" ? "1" : "0",
  },
  ...(isDesktopExport
    ? {
        output: "export",
        trailingSlash: true,
      }
    : {})
};

export default nextConfig;
