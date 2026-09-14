import { useEffect, useState, type ReactNode, type RefObject } from "react";

export function ReaderNavigation({frame, version, menuOpen, onToggle, onCollapse, children}: {
  frame: RefObject<HTMLIFrameElement | null>; version: string; menuOpen: boolean; onToggle: () => void; onCollapse?: (collapsed: boolean) => void; children?: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [items, setItems] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    setItems([]); setOpen(false); setCollapsed(false); onCollapse?.(false);
    const receive = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow) return;
      if (event.data?.type === "openatlas:scroll" && typeof event.data.y === "number" && Number.isFinite(event.data.y)) {
        if(event.data.y > 100) {setCollapsed(true);onCollapse?.(true);}
        else if(event.data.y < 32) {setCollapsed(false);onCollapse?.(false);}
        return;
      }
      if (event.data?.type !== "openatlas:outline") return;
      if (Array.isArray(event.data.items) && event.data.items.length <= 150 && event.data.items.every((x: unknown) => typeof x === "string" && x.length <= 160)) setItems(event.data.items);
    };
    const escape = (event: KeyboardEvent) => {if(event.key === "Escape") setOpen(false);};
    window.addEventListener("message", receive); window.addEventListener("keydown", escape);
    frame.current?.contentWindow?.postMessage({type:"openatlas:outline-request"},"*");
    return () => {window.removeEventListener("message", receive);window.removeEventListener("keydown", escape);};
  }, [frame, version, onCollapse]);
  return <>
    {open && <button className="reader-shade" aria-label="Close contents" onClick={()=>setOpen(false)}/>}
    <nav className={"reader-mini-menu " + (collapsed ? "is-collapsed" : "is-expanded")} aria-label="Notebook navigation">
      <a className="reader-back" href="/" aria-label="Back to library" title="Back to library"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="m10 5-7 7 7 7M3 12h18"/></svg></a>
      <a className="reader-wordmark" href="/" aria-label="OpenAtlas home"><svg aria-hidden="true" width="23" height="23" viewBox="0 0 28 28" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M4 6c4-1 7 0 10 3 3-3 6-4 10-3v16c-4-1-7 0-10 2-3-2-6-3-10-2V6ZM14 9v15M8 11l3 1M18 12l3-1"/></svg><span>OpenAtlas</span></a>
      <div className="reader-mini-actions">
        {!collapsed && <div className="reader-full-actions">{children}</div>}
        <button className="reader-more" aria-label={menuOpen ? "Close reader controls" : "Open Notebook menu"} aria-expanded={menuOpen} onClick={()=>{setOpen(false);onToggle();}}>···</button>
        <button className="reader-contents" aria-label="Contents" aria-expanded={open} aria-controls="reader-outline" onClick={()=>{if(menuOpen) onToggle();setOpen(!open);}}><svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M9 6h11M9 12h8M9 18h11M4 6h.01M4 12h.01M4 18h.01"/></svg><span>Contents</span></button>
      </div>
      {open && <section id="reader-outline" className="reader-outline" aria-label="Table of contents"><p>IN THIS NOTEBOOK</p>{items.length ? items.map((title,index)=><button key={index} onClick={()=>{frame.current?.contentWindow?.postMessage({type:"openatlas:section",index},"*");setOpen(false);frame.current?.focus();}}>{title}</button>) : <p>No section headings available.</p>}</section>}
    </nav>
  </>;
}
