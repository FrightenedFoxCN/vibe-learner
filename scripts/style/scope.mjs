const jsExtension = /\.(?:[cm]?js|jsx|tsx?)$/u;

export function sourceKind(path) {
  if (
    /(?:^|\/)(?:node_modules|\.next|dist|dist-test|out|build|target|data|\.venv)\//u.test(
      path,
    ) ||
    path.endsWith("next-env.d.ts")
  )
    return null;
  if (
    !/^(?:apps\/|packages\/|services\/ai\/|tools\/|scripts\/)/u.test(path) &&
    path.includes("/")
  )
    return null;
  if (path.endsWith(".py")) return "python";
  return jsExtension.test(path) ? "javascript" : null;
}
