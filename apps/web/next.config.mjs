const isDesktopExport =
  process.env.npm_lifecycle_event === "build:desktop" ||
  process.env.VIBE_LEARNER_DESKTOP_EXPORT === "1";

/** @type {import('next').NextConfig} */
const nextConfig = {
  typedRoutes: true,
  ...(isDesktopExport
    ? {
        output: "export",
        trailingSlash: true,
      }
    : {})
};

export default nextConfig;
