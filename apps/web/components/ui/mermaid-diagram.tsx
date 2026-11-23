"use client";

import { useEffect, useId, useState } from "react";

interface MermaidDiagramProps {
  chart: string;
}

export function MermaidDiagram({ chart }: MermaidDiagramProps) {
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");
  const diagramId = useId().replace(/[:]/g, "-");

  useEffect(() => {
    let cancelled = false;

    async function renderChart() {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "neutral",
        });
        const { svg: nextSvg } = await mermaid.render(`mermaid-${diagramId}`, chart);
        if (cancelled) {
          return;
        }
        setSvg(nextSvg);
        setError("");
      } catch (renderError) {
        if (cancelled) {
          return;
        }
        setSvg("");
        setError(renderError instanceof Error ? renderError.message : "图表渲染失败");
      }
    }

    void renderChart();
    return () => {
      cancelled = true;
    };
  }, [chart, diagramId]);

  if (error) {
    return (
      <div className="mb-2.5 grid gap-2 border border-negative/25 bg-negative/5 px-3.5 py-3">
        <strong className="text-xs text-negative">Mermaid 图表渲染失败</strong>
        <pre className="m-0 overflow-x-auto border border-negative/20 bg-bg px-3 py-2.5 text-xs leading-[1.6]">
          {chart}
        </pre>
        <p className="m-0 wrap-anywhere text-xs leading-normal text-negative">
          {error}
        </p>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="mb-2.5 border border-border bg-panel px-3.5 py-3 text-xs text-muted">
        Mermaid 图表渲染中…
      </div>
    );
  }

  return (
    <div
      className="mb-2.5 overflow-x-auto border border-border bg-panel px-3.5 py-3"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
