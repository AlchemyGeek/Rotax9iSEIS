import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart, ScatterChart, CustomChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkAreaComponent,
  MarkLineComponent,
  AxisPointerComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";

echarts.use([
  LineChart,
  ScatterChart,
  CustomChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkAreaComponent,
  MarkLineComponent,
  AxisPointerComponent,
  CanvasRenderer,
]);

// The one shared chart wrapper (Spec 03 §6.1): a thin imperative-echarts
// binding, reused for Flight view's timeline and Trends' scatter. It owns
// nothing about chart *shape* — that's each caller's `option`, including
// any zoom range (as dataZoom start/end percentages baked into the option
// itself — imperative dispatchAction-after-the-fact zooming proved
// unreliable and was replaced by this simpler, single-code-path approach).
export interface EChartBaseProps {
  option: EChartsOption;
  height: number | string;
  onZoom?: (startValue: number, endValue: number) => void;
  // Fires from a second (Y-axis) dataZoom component, if the caller's
  // option defines one at dataZoom[1] — kept separate from onZoom rather
  // than folded into one callback so single-axis callers (ChannelTimeline)
  // are untouched.
  onZoomY?: (startValue: number, endValue: number) => void;
}

export function EChartBase({ option, height, onZoom, onZoomY }: EChartBaseProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = echarts.init(containerRef.current, null, { renderer: "canvas" });
    chartRef.current = chart;

    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(containerRef.current);

    if (onZoom || onZoomY) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      chart.on("dataZoom", (params: any) => {
        const opt = chart.getOption();
        const dzList = opt.dataZoom as { startValue?: number; endValue?: number }[] | undefined;
        const dzX = dzList?.[0];
        const dzY = dzList?.[1];

        // Single-axis callers (ChannelTimeline) have exactly one dataZoom
        // component, so there's nothing to disambiguate — any event on
        // this chart is *the* zoom/pan, full stop. Fire unconditionally.
        if (!onZoomY) {
          if (onZoom && dzX && dzX.startValue !== undefined && dzX.endValue !== undefined) {
            onZoom(dzX.startValue, dzX.endValue);
          }
          return;
        }

        // Two-axis callers (Trends) need to know *which* component a
        // given gesture actually moved (an x-only wheel-zoom shouldn't
        // report a y-pan) — matched by id, which both a programmatic
        // dispatchAction and a real mouse/wheel-driven roam gesture
        // populate consistently, unlike dataZoomIndex, which a real
        // gesture doesn't reliably set (verified: dispatchAction calls
        // that explicitly pass dataZoomIndex echo it back, but that
        // doesn't prove a real roam event does the same — matching on it
        // silently dropped every real-gesture event on a single-axis
        // chart, which is the bug this whole rewrite fixes).
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const events: any[] = params?.batch ?? [params];
        const changedIds = new Set(events.map((p) => p?.dataZoomId).filter(Boolean));
        const dzXWithId = dzX as { id?: string } | undefined;
        const dzYWithId = dzY as { id?: string } | undefined;

        if (onZoom && dzX && dzXWithId?.id && changedIds.has(dzXWithId.id) && dzX.startValue !== undefined && dzX.endValue !== undefined) {
          onZoom(dzX.startValue, dzX.endValue);
        }
        if (onZoomY && dzY && dzYWithId?.id && changedIds.has(dzYWithId.id) && dzY.startValue !== undefined && dzY.endValue !== undefined) {
          onZoomY(dzY.startValue, dzY.endValue);
        }
      });
    }

    return () => {
      resizeObserver.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true });
  }, [option]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
