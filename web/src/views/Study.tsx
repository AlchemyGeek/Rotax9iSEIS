import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { EngineRpcError, getEngineClient } from "../lib/engineClient";
import { NotebookView, isNotebookView, type NotebookStudyView } from "../components/research/NotebookView";
import { LINK, MUTED } from "../components/research/ui";

const client = getEngineClient();

// Spec 16 §5.3, D15 — a study is a notebook: /research/<id> renders it.
// The hand-study page (selection, slice rules, the Signal and Compare
// screens, the question forms) is retired with Spec 06 v1.0; a study stored
// the old way arrives here already converted by the host.
export function Study() {
  const { studyId } = useParams();
  const navigate = useNavigate();
  const [view, setView] = useState<NotebookStudyView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setView(null);
    setError(null);
    (async () => {
      try {
        const doc = await client.loadStudy(studyId!);
        if (!live) return;
        if (isNotebookView(doc)) setView(doc);
        else setError("This study can't be shown.");
      } catch (e) {
        if (!live) return;
        setError(e instanceof EngineRpcError && e.code === "NO_ACTIVE_WORKSPACE" ? "Open a workspace first."
          : e instanceof EngineRpcError && e.code === "NOT_FOUND" ? "There is no such notebook in this workspace."
          : e instanceof Error ? e.message : String(e));
      }
    })();
    return () => { live = false; };
  }, [studyId]);

  return (
    <NavShell>
      <div style={{ width: "100%", overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 10 }} data-testid="study-page">
        <div><button type="button" onClick={() => navigate("/research")} style={LINK}>← Research</button></div>
        {view && view.study_id === studyId
          ? <NotebookView view={view} onChanged={setView} onDeleted={() => navigate("/research")} />
          : <div style={MUTED} data-testid="study-status">{error ?? "Loading…"}</div>}
      </div>
    </NavShell>
  );
}
