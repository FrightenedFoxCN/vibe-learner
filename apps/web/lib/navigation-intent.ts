interface LinkClick {
  button: number;
  defaultPrevented: boolean;
  metaKey: boolean;
  altKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
}

/** Only ordinary, same-tab app navigation belongs to the custom guard. */
export function classifyAppLink(
  event: LinkClick,
  anchor: { href: string; target: string; hasAttribute(name: string): boolean },
  sourceHref: string,
): { path: string; suffix: string; samePage: boolean } | null {
  if (
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.altKey ||
    event.ctrlKey ||
    event.shiftKey ||
    (anchor.target && anchor.target.toLowerCase() !== "_self") ||
    anchor.hasAttribute("download")
  )
    return null;
  const source = new URL(sourceHref);
  const destination = new URL(anchor.href, source);
  if (destination.protocol !== source.protocol || destination.origin !== source.origin)
    return null;
  const path = destination.pathname.replace(/\/+$/, "") || "/";
  const sourcePath = source.pathname.replace(/\/+$/, "") || "/";
  return {
    path,
    suffix: destination.search + destination.hash,
    samePage: path === sourcePath && destination.search === source.search,
  };
}
