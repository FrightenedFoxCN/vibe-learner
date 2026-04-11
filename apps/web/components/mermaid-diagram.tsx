"use client";

import { useEffect, useId, useState } from "react";
import type { CSSProperties } from "react";

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
      <div style={styles.errorWrap}>
        <strong style={styles.errorTitle}>Mermaid 图表渲染失败</strong>
        <pre style={styles.errorCode}>{chart}</pre>
        <p style={styles.errorText}>{error}</p>
      </div>
    );
  }

  if (!svg) {
    return <div style={styles.loading}>Mermaid 图表渲染中…</div>;
  }

  return <div style={styles.diagram} dangerouslySetInnerHTML={{ __html: svg }} />;
}

const styles: Record<string, CSSProperties> = {
  diagram: {
    margin: "0 0 10px",
    padding: "12px 14px",
    border: "1px solid var(--border)",
    background: "#f8fbfc",
    overflowX: "auto",
  },
  loading: {
    margin: "0 0 10px",
    padding: "12px 14px",
    border: "1px solid var(--border)",
    background: "#f8fbfc",
    color: "var(--muted)",
    fontSize: 12,
  },
  errorWrap: {
    display: "grid",
    gap: 8,
    margin: "0 0 10px",
    padding: "12px 14px",
    border: "1px solid #f0c2c2",
    background: "#fff7f7",
  },
  errorTitle: {
    fontSize: 12,
    color: "#9f1d1d",
  },
  errorCode: {
    margin: 0,
    padding: "10px 12px",
    border: "1px solid #f0d1d1",
    background: "white",
    overflowX: "auto",
    fontSize: 12,
    lineHeight: 1.6,
  },
  errorText: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.5,
    color: "#7f1d1d",
    wordBreak: "break-word",
  },
};
