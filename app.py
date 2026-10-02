# -*- coding: utf-8 -*-
"""
Clinical Review Assistant - the screen.

Four pages:
    Overview    one upload box for everything, what is in the study, the old
                vs new TLF comparison, and the Scan button
    Findings    every finding, one tab per layer, Keep / Reject, and what the
                agent concluded for each
    Agent       run the agent on findings (investigate, fix, query), chat with
                the study, and read every fix and query it drafted
    Visualize   the findings as charts

There is no logic in this file. Everything happens in the cra package.
"""
import os
import tempfile
import pandas as pd
import streamlit as st

from cra.study import (KINDS, KIND_LABEL, classify, save_upload, save_zip,
                       studies, inventory, new_study, remove_file, load_study)
from cra.scan_study import scan, save_decision, NOT_CHECKED, load_history
from cra.excel_out import write_scan_workbook, status_of
from cra.flags import LAYERS
from cra.compare_tlf import compare, totals
from cra.agent.tasks import Agent, results as agent_results, save_explanation
from cra import explore
from cra.agent.loop import live, agent_model
from cra.model import current_mode
from cra import viz

ROOT = "studies"
st.set_page_config(page_title="Clinical Review Assistant", page_icon="✅",
                   layout="wide")

SEV_COLOUR = dict(zip(viz.SEV, viz.SEV_COL))
VERDICT = {"confirmed": ("Confirmed", "#0ca30c"),
           "likely_false_alarm": ("Likely false alarm", "#2a78d6"),
           "needs_person": ("Needs a person", "#ec835a")}
WHAT_IT_UNLOCKS = {
    "raw": "raw vs SDTM: lost subjects and records, bad dates, text in numbers",
    "sdtm": "cross-domain checks, study days, CDISC structure and terminology",
    "adam": "ADSL vs DM, flags vs dosing, BASE and CHG re-derived, TLF Ns",
    "tlf": "every output check, and output numbers against ADaM",
    "tlf_old": "old vs new comparison of every output",
    "sap": "populations, treatments, parameters and planned outputs",
    "shells": "missing outputs, outputs with no shell, title wording",
    "specs": "variables, labels and types against the data",
}

st.markdown("""<style>
.block-container{padding-top:1.6rem;max-width:1320px}
.kcard{border:1px solid #E1E6EC;border-radius:10px;padding:10px 11px;
       min-height:122px;background:#FAFBFC}
.kcard h4{margin:0 0 2px 0;font-size:.9rem}
.kcard .n{font-size:1.45rem;font-weight:700;color:#0F7B6C}
.kcard .none{font-size:1.45rem;font-weight:700;color:#B0B8C1}
.kcard p{font-size:.72rem;color:#5A6B7B;margin:2px 0 0 0;line-height:1.25}
.sev{font-weight:700;font-size:.8rem;padding:1px 8px;border-radius:9px;
     color:white;margin-right:6px}
.tag{font-size:.75rem;color:#52514e;border:1px solid #D5DBE2;border-radius:9px;
     padding:0 7px;margin-right:4px}
.vtag{font-size:.75rem;font-weight:600;border-radius:9px;padding:1px 8px;
      margin-right:4px;border:1.5px solid}
.engine{padding:8px 12px;border-radius:8px;font-size:.9rem;margin-bottom:8px}
.tile{border:1px solid #E1E6EC;border-radius:10px;padding:10px 14px;
      background:#fcfcfb}
.tile .v{font-size:1.8rem;font-weight:700;color:#0b0b0b;line-height:1.2}
.tile .l{font-size:.8rem;color:#52514e}
.xhead{background:#14335f;color:#fff;border-radius:10px;padding:12px 18px;
       display:flex;align-items:center;gap:14px;margin-bottom:6px}
.xhead .t{font-size:1.15rem;font-weight:700}
.xhead .s{opacity:.8;border-left:1px solid rgba(255,255,255,.35);padding-left:14px}
.xhead .badge{margin-left:auto;background:#fde7b0;color:#5a3d00;font-weight:700;
       font-size:.75rem;padding:3px 10px;border-radius:6px}
.xhead .state{font-size:.85rem;opacity:.9}
.panel-h{font-size:1.15rem;font-weight:700;color:#14335f;margin:0 0 4px 0}
.msg{border-radius:10px;padding:8px 11px;margin:6px 0;font-size:.88rem;
     line-height:1.35}
.msg.you{background:#eef3f8}.msg.ai{background:#f3f7f6;border:1px solid #e1ebe8}
.msg .who{font-size:.72rem;font-weight:700;color:#14335f;margin-bottom:2px}
.sec{display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #eceae4}
.sec .ic{font-size:1.25rem;width:34px;height:34px;border-radius:50%;
         background:#e8f3f1;display:flex;align-items:center;justify-content:center;
         flex-shrink:0}
.sec.warn .ic{background:#fdeee6}
.sec h5{margin:0 0 3px 0;color:#14335f;font-size:.95rem}
.sec p{margin:0;font-size:.86rem;color:#2c2c2a;line-height:1.4}
.chip{background:#dbe8fb;color:#184f95;font-weight:700;font-size:.75rem;
      border-radius:6px;padding:2px 8px;margin-left:6px}
.foot{font-size:.75rem;color:#898781;margin-top:6px}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- state
def folder_of(name):
    return os.path.join(ROOT, name)


@st.cache_resource(show_spinner=False)
def _load(folder, version):
    return load_study(folder)


def study_obj(name):
    return _load(folder_of(name), st.session_state.get("ver", 0))


def bump():
    """Files changed: forget the loaded study, the scan and the agent."""
    st.session_state.ver = st.session_state.get("ver", 0) + 1
    for k in ("res", "agent", "chat"):
        st.session_state.pop(k, None)


# ---------------------------------------------------------------- sidebar
st.sidebar.title("Clinical Review Assistant")
names = studies(ROOT)
with st.sidebar.expander("New study", expanded=not names):
    new_name = st.text_input("Study name", placeholder="ABC-123")
    if st.button("Create", disabled=not new_name.strip()):
        st.session_state.study = os.path.basename(new_study(ROOT, new_name))
        bump()
        st.rerun()

if not names:
    st.info("Create a study on the left, or run  python make_sample_study.py  "
            "for the demo.")
    st.stop()

default = st.session_state.get("study")
study = st.sidebar.selectbox("Study", names,
                             index=names.index(default) if default in names else 0)
if st.session_state.get("study") != study:
    st.session_state.study = study
    for k in ("res", "agent", "chat"):
        st.session_state.pop(k, None)
folder = folder_of(study)

use_model = st.sidebar.toggle(
    "Use the AI model", value=live(), disabled=not live(),
    help="Needs CRA_MODEL_MODE and CRA_API_KEY in .env. Without a key, the "
         "offline agent and every check still work.")
PAGES = ["Overview", "Findings", "Explore", "Agent", "Visualize"]
if "goto" in st.session_state:          # a button asked for another page
    st.session_state.page = st.session_state.pop("goto")
if st.session_state.get("page") not in PAGES:
    st.session_state.page = "Overview"
page = st.sidebar.radio("Page", PAGES, key="page")

res = st.session_state.get("res")
if res:
    st.sidebar.divider()
    c = res.counts()
    tot = {s: sum(c.get(l, {}).get(s, 0) for l in LAYERS) for s in viz.SEV}
    st.sidebar.metric("Findings", len(res.findings))
    st.sidebar.caption("%d Critical · %d Major · %d Minor"
                       % (tot["Critical"], tot["Major"], tot["Minor"]))
    st.sidebar.caption("Scanned %s" % res.run_at)
st.sidebar.caption("Agent: %s" % ("AI · %s %s" % (current_mode(),
                                                  agent_model(current_mode()))
                                  if live() and use_model
                                  else "offline (no API key)"))


def run_scan():
    with st.spinner("Scanning raw, SDTM, ADaM, TLF, SAP and shells..."):
        st.session_state.res = scan(folder, use_model=use_model and live())
    st.session_state.pop("agent", None)


def get_agent():
    a = st.session_state.get("agent")
    if a is None:
        a = Agent(folder, st.session_state.res.findings,
                  use_model=use_model and live())
        st.session_state.agent = a
    return a


def need_scan():
    st.info("No scan yet for this study.")
    if st.button("Run scan", type="primary"):
        run_scan()
        st.rerun()
    st.stop()


def tile(col, value, label):
    col.markdown("<div class='tile'><div class='v'>%s</div><div class='l'>%s"
                 "</div></div>" % (value, label), unsafe_allow_html=True)


def show_steps(run):
    with st.expander("What the agent did (%d step%s · %s%s)" % (
            len(run.steps), "" if len(run.steps) == 1 else "s", run.engine,
            ", %d tokens" % (run.tokens_in + run.tokens_out)
            if run.tokens_in else "")):
        for i, s in enumerate(run.steps, 1):
            args = ", ".join("%s=%r" % kv for kv in s.args.items()
                             if kv[0] not in ("text", "reason"))
            st.markdown("**%d. %s**(%s)" % (i, s.tool, args))
            st.code(s.result[:1200], language=None)


# ================================================================ Overview
if page == "Overview":
    st.header(study)

    st.subheader("Add files")
    st.caption("Drop everything at once: raw data, SDTM, ADaM, TLF outputs, "
               "the previous TLF delivery, the SAP, mock shells and specs. A "
               "zip works too. Each file is sorted by its name; change the "
               "guess before you add them.")
    files = st.file_uploader(
        "Files", accept_multiple_files=True, label_visibility="collapsed",
        type=["xpt", "sas7bdat", "csv", "rtf", "docx", "pdf", "txt", "xlsx",
              "xls", "zip"], key="up%d" % st.session_state.get("ver", 0))
    if files:
        picks = {}
        for f in files:
            if f.name.lower().endswith(".zip"):
                st.write("📦 **%s**: unpacked and sorted file by file" % f.name)
                picks[f.name] = "zip"
                continue
            guess = classify(f.name) or "sap"
            a, b = st.columns([3, 2])
            a.write(f.name)
            picks[f.name] = b.selectbox(
                "goes to", KINDS, index=KINDS.index(guess),
                format_func=KIND_LABEL.get, key="k_" + f.name,
                label_visibility="collapsed")
        if st.button("Add %d file(s)" % len(files), type="primary"):
            added = {}
            for f in files:
                if picks[f.name] == "zip":
                    with tempfile.NamedTemporaryFile(suffix=".zip",
                                                     delete=False) as tmp:
                        tmp.write(f.getvalue())
                    for k, n in save_zip(folder, tmp.name).items():
                        added[k] = added.get(k, 0) + n
                    os.unlink(tmp.name)
                else:
                    k = save_upload(folder, f.name, f.getvalue(), picks[f.name])
                    added[k] = added.get(k, 0) + 1
            bump()
            st.toast("Added " + ", ".join("%d %s" % (n, KIND_LABEL[k])
                                          for k, n in added.items()))
            st.rerun()

    st.subheader("In this study")
    inv = inventory(folder)
    cols = st.columns(len(KINDS))
    for col, k in zip(cols, KINDS):
        n = len(inv[k])
        col.markdown(
            "<div class='kcard'><h4>%s</h4><div class='%s'>%s</div><p>%s</p>"
            "</div>" % (KIND_LABEL[k], "n" if n else "none", n if n else "—",
                        WHAT_IT_UNLOCKS[k] if n else "not uploaded: these "
                        "checks will not run"), unsafe_allow_html=True)
    with st.expander("Browse files"):
        for k in KINDS:
            if not inv[k]:
                continue
            st.markdown("**%s**" % KIND_LABEL[k])
            for name in inv[k]:
                a, b = st.columns([6, 1])
                a.write(name)
                if b.button("Remove", key="rm_%s_%s" % (k, name)):
                    remove_file(folder, k, name)
                    bump()
                    st.rerun()

    # ---- old vs new TLF -------------------------------------------------
    st.divider()
    st.subheader("Compare with the previous TLF delivery")
    old_up = st.file_uploader(
        "Previous delivery (.rtf or a zip of them)", accept_multiple_files=True,
        type=["rtf", "zip"], key="old%d" % st.session_state.get("ver", 0))
    if old_up and st.button("Add as previous delivery"):
        for f in old_up:
            if f.name.lower().endswith(".zip"):
                with tempfile.NamedTemporaryFile(suffix=".zip",
                                                 delete=False) as tmp:
                    tmp.write(f.getvalue())
                import zipfile
                with zipfile.ZipFile(tmp.name) as z:
                    for info in z.infolist():
                        if info.filename.lower().endswith(".rtf"):
                            save_upload(folder, info.filename, z.read(info),
                                        "tlf_old")
                os.unlink(tmp.name)
            else:
                save_upload(folder, f.name, f.getvalue(), "tlf_old")
        bump()
        st.rerun()

    if inv["tlf_old"] and inv["tlf"]:
        diffs = compare(os.path.join(folder, "tlf_old"),
                        os.path.join(folder, "tlf"))
        t = totals(diffs)
        c = st.columns(5)
        tile(c[0], t["changed"], "outputs changed")
        tile(c[1], t["new"], "new outputs")
        tile(c[2], t["removed"], "removed outputs")
        tile(c[3], t["same"], "unchanged")
        tile(c[4], t["cells"], "table cells changed")
        st.caption("A new run date on the Source line is not counted as a "
                   "change. A different program or version is.")
        show_same = st.checkbox("Show unchanged outputs too")
        st.dataframe(pd.DataFrame(
            [{"Output": d.new_file or d.old_file, "Number": d.output_id,
              "Status": d.status, "What changed": d.summary()}
             for d in diffs if show_same or d.status != "same"]),
            hide_index=True, width="stretch")
        changed = [d for d in diffs if d.status == "changed"]
        if changed:
            pick = st.selectbox("See the changes in", [d.new_file for d in changed])
            d = next(x for x in changed if x.new_file == pick)
            st.dataframe(pd.DataFrame([{"What": c.kind, "Where": c.where,
                                        "Previous": c.old, "Now": c.new}
                                       for c in d.changes]),
                         hide_index=True, width="stretch")
    elif inv["tlf"]:
        st.caption("Add the previous delivery's RTF files here to see what "
                   "changed: titles, footnotes, headers, every table cell, "
                   "outputs added or removed.")

    # ---- scan -----------------------------------------------------------
    st.divider()
    a, b = st.columns([1, 4])
    if a.button("Run scan", type="primary", width="stretch"):
        run_scan()
        st.rerun()
    b.caption("Checks everything uploaded. Each layer gets its own tab on the "
              "Findings page and in the Excel sheet.")
    if res:
        counts = res.counts()
        st.dataframe(
            [{"Layer": l, "Critical": counts.get(l, {}).get("Critical", 0),
              "Major": counts.get(l, {}).get("Major", 0),
              "Minor": counts.get(l, {}).get("Minor", 0),
              "Total": sum(counts.get(l, {}).values())} for l in LAYERS],
            hide_index=True, width="stretch")
        with st.expander("What happened"):
            for line in res.log:
                st.write("- " + line)
        with st.expander("What the scan does NOT look at"):
            for line in NOT_CHECKED:
                st.write("- " + line)


# ================================================================ Findings
elif page == "Findings":
    st.header("Findings")
    if not res:
        need_scan()
    done = agent_results(folder)

    a, b, c = st.columns([2, 2, 1])
    sevs = a.multiselect("Severity", viz.SEV, default=viz.SEV)
    all_status = ["Confirmed", "To check", "Kept by model", "Kept"]
    stats = b.multiselect("Status", all_status, default=all_status)
    path = os.path.join("out", "%s_scan.xlsx" % study)
    write_scan_workbook(res, path, NOT_CHECKED, agent=done)
    with open(path, "rb") as fh:
        c.download_button("⬇ Excel sheet", fh.read(),
                          file_name=os.path.basename(path), width="stretch")

    def card(f):
        e = done.get(f.key)
        with st.container(border=True):
            v = ""
            if e and e.get("verdict"):
                label, colour = VERDICT[e["verdict"]]
                v = ("<span class='vtag' style='color:%s;border-color:%s'>"
                     "Agent: %s</span>" % (colour, colour, label))
            st.markdown(
                "<span class='sev' style='background:%s'>%s</span>"
                "<span class='tag'>%s</span><span class='tag'>%s</span>%s<br>"
                "<b>%s</b>" % (SEV_COLOUR.get(f.severity, "#52514e"),
                               f.severity, f.area, status_of(f), v, f.finding),
                unsafe_allow_html=True)
            st.write(f.what_is_wrong)
            st.caption("Output / File: " + f.output_file)
            with st.expander("Evidence"):
                st.write(f.evidence)
                st.caption("Found by %s. Every number here was counted by "
                           "code." % f.found_by)
            if e:
                with st.expander("Agent: verdict, fix and query"):
                    if e.get("reason"):
                        st.write(e["reason"])
                    for x in e.get("fixes", []):
                        st.caption("Suggested fix (%s)" % x["kind"])
                        st.code(x["text"], language="sas" if x["kind"] == "sas"
                                else None)
                    for q in e.get("queries", []):
                        st.caption("Draft query to %s: %s"
                                   % (q["to"].replace("_", " "), q["subject"]))
                        st.code(q["text"], language=None, wrap_lines=True)
                    st.caption("By %s, %s" % (e.get("by", ""), e.get("at", "")))
            k1, k2, k3, k4, _ = st.columns([1, 1, 1.6, 1.4, 3])
            if k4.button("Explore", key="x" + f.key, type="primary"):
                st.session_state.explore_key = f.key
                st.session_state.goto = "Explore"
                st.rerun()
            if k1.button("Keep", key="k" + f.key,
                         disabled=f.decision == "accepted"):
                save_decision(folder, f.key, "accepted")
                f.decision = "accepted"
                st.rerun()
            if k2.button("Reject", key="r" + f.key):
                save_decision(folder, f.key, "rejected")
                res.findings = [x for x in res.findings if x.key != f.key]
                st.session_state.pop("agent", None)
                st.toast("Rejected. It will not come back on the next scan.")
                st.rerun()
            if k3.button("Run agent", key="g" + f.key):
                with st.spinner("Agent working..."):
                    st.session_state["last_run_" + f.key] = get_agent().work(f)
                st.rerun()
            last = st.session_state.get("last_run_" + f.key)
            if last:
                (st.info if last.ok else st.warning)(last.answer)
                show_steps(last)

    shown = [f for f in res.findings
             if f.severity in sevs and status_of(f) in stats]
    tabs = st.tabs(["All (%d)" % len(shown)] +
                   ["%s (%d)" % (l, len([f for f in shown if f.layer == l]))
                    for l in LAYERS])
    with tabs[0]:
        st.dataframe(
            [{"Layer": f.layer, "Severity": f.severity, "Area": f.area,
              "Finding": f.finding, "Output / File": f.output_file,
              "Status": status_of(f),
              "Agent": VERDICT.get(done.get(f.key, {}).get("verdict"),
                                   ("", ""))[0]} for f in shown],
            hide_index=True, width="stretch", height=520)
    for tab, layer in zip(tabs[1:], LAYERS):
        with tab:
            items = [f for f in shown if f.layer == layer]
            if not items:
                st.success("Nothing found in this layer, or nothing uploaded "
                           "for it.")
            for f in items:
                card(f)


# ================================================================ Explore
elif page == "Explore":
    if not res:
        need_scan()
    findings = res.findings
    keys = [f.key for f in findings]
    if st.session_state.get("explore_key") not in keys:
        st.session_state.explore_key = keys[0]
    done = agent_results(folder)
    f = next(x for x in findings if x.key == st.session_state.explore_key)
    expl = done.get(f.key, {}).get("explanation", {})
    state = {"draft": "Draft · awaiting review",
             "submitted": "Submitted · awaiting approval",
             "approved": "Approved", "sent_back": "Sent back for changes"}.get(
        expl.get("status", "draft"), "Draft")
    st.markdown("<div class='xhead'><span class='t'>Explore finding</span>"
                "<span class='s'>Study: %s</span><span class='badge'>%s</span>"
                "<span class='state'>%s</span></div>"
                % (study, f.severity.upper() + " · " + f.layer, state),
                unsafe_allow_html=True)

    # ---- which finding ----------------------------------------------------
    a, b, c = st.columns([7, 1, 1])
    idx = keys.index(f.key)
    label = {x.key: "[%s] %s · %s" % (x.severity, x.layer, x.finding)
             for x in findings}
    pick = a.selectbox("Finding", keys, index=idx, format_func=label.get,
                       label_visibility="collapsed")
    if b.button("◀ Prev", width="stretch", disabled=idx == 0):
        pick = keys[idx - 1]
    if c.button("Next ▶", width="stretch", disabled=idx == len(keys) - 1):
        pick = keys[idx + 1]
    if pick != f.key:
        st.session_state.explore_key = pick
        st.rerun()

    stdy = study_obj(study)
    ev = explore.build(f, stdy)
    st.caption("%s · %s · %s" % (f.area, status_of(f), f.output_file))

    left, mid, right = st.columns([1, 1.6, 1.2], gap="medium")

    # ---- conversation -----------------------------------------------------
    with left:
        with st.container(border=True):
            st.markdown("<div class='panel-h'>Conversation</div>",
                        unsafe_allow_html=True)
            convo = st.session_state.setdefault("xchat", {}).setdefault(f.key, [])
            box = st.container(height=390)
            with box:
                if not convo:
                    st.caption("Ask about this finding. Code answers with the "
                               "numbers; %s." % ("the AI words the reply"
                                                 if live() and use_model
                                                 else "no API key, so replies "
                                                 "are from code and templates"))
                for who, text in convo:
                    st.markdown("<div class='msg %s'><div class='who'>%s</div>%s"
                                "</div>" % ("you" if who == "You" else "ai", who,
                                            text.replace("\n", "<br>")),
                                unsafe_allow_html=True)
            quick = None
            if st.button("Why does it matter?", key="qa" + f.key,
                         width="stretch"):
                quick = "Why does this matter?"
            if st.button("How do I confirm it?", key="qb" + f.key,
                         width="stretch"):
                quick = "How do I confirm it?"
            if st.button("Draft a fix", key="qc" + f.key, width="stretch"):
                quick = "Draft a fix."
            with st.form("ask" + f.key, clear_on_submit=True, border=False):
                cc1, cc2 = st.columns([2.4, 1.3])
                typed = cc1.text_input("Ask", placeholder="Ask a follow-up "
                                       "question...", label_visibility="collapsed")
                sent = cc2.form_submit_button("Send", type="primary")
            q = quick or (typed if sent and typed.strip() else None)
            if q:
                ag = get_agent()
                with st.spinner("Working..."):
                    if live() and use_model:
                        run = ag.chat("About finding %s (%s). %s"
                                      % (f.key, f.finding, q),
                                      history=[(convo[i][1], convo[i + 1][1])
                                               for i in range(0, len(convo) - 1, 2)])
                        reply = run.answer
                        st.session_state["xlog_" + f.key] = run
                    elif quick == "Why does this matter?":
                        reply = f.what_is_wrong + "\n\nEvidence: " + f.evidence
                    elif quick == "How do I confirm it?":
                        reply = ("%s\n\nRe-run this on %s:\n%s"
                                 % (ev.how_to_read, ", ".join(ev.datasets)
                                    or f.output_file, ev.code))
                    elif quick == "Draft a fix.":
                        run = ag.work(f, ("fix",))
                        st.session_state["xlog_" + f.key] = run
                        fx = agent_results(folder).get(f.key, {}).get("fixes", [])
                        reply = "\n\n".join("%s:\n%s" % (x["kind"].upper(),
                                                         x["text"]) for x in fx) \
                            or run.answer
                    else:
                        run = ag.chat(q)
                        st.session_state["xlog_" + f.key] = run
                        reply = run.answer
                convo += [("You", q), ("Clinical Review Assistant", reply)]
                st.rerun()

    # ---- graphs, data used, log ------------------------------------------
    with mid:
        with st.container(border=True):
            st.markdown("<div class='panel-h'>Graph</div>", unsafe_allow_html=True)
            st.caption(ev.title)
            if ev.chart is not None:
                st.altair_chart(ev.chart, width="stretch", theme=None)
            else:
                st.info(ev.how_to_read)
        with st.container(border=True):
            head = st.empty()
            src = st.segmented_control(
                "Data source", ["Finding", "Raw", "SDTM", "ADaM"],
                default="Finding", key="src" + f.key,
                label_visibility="collapsed")
            if src in (None, "Finding"):
                t, chip = ev.table, ev.table_source
            else:
                group = {"Raw": stdy.raw, "SDTM": stdy.sdtm,
                         "ADaM": stdy.adam}[src]
                if not group:
                    t, chip = None, src
                    st.caption("No %s data in this study." % src)
                else:
                    dsn = st.selectbox("Dataset", sorted(group),
                                       key="dsn" + f.key)
                    full = group[dsn]["data"]
                    chip = dsn
                    subj = next((c for c in ("USUBJID", "SUBJID", "SUBJECT")
                                 if c in full.columns), None)
                    shorts = {str(x).split("-")[-1] for x in ev.flagged}
                    if subj and shorts:
                        mask = full[subj].astype(str).str.split("-").str[-1] \
                            .isin(shorts)
                        t = full[mask].copy()
                        t.insert(0, "Flag", "⚠ flagged subject")
                        st.caption("Records of the flagged subjects in %s." % dsn)
                    else:
                        t = full.head(50)
            head.markdown("<span class='panel-h'>Data used</span>%s"
                          % ("<span class='chip'>%s</span>" % chip
                             if chip else ""), unsafe_allow_html=True)
            if t is not None and len(t):
                full_view = st.toggle("View all rows", key="full" + f.key)
                show = explore.tidy(t if full_view else t.head(12))
                if "Flag" in show.columns:
                    styled = show.style.apply(
                        lambda r: ["background-color:#fde7dc" if r["Flag"]
                                   else "" for _ in r], axis=1)
                    st.dataframe(styled, hide_index=True, width="stretch")
                else:
                    st.dataframe(show, hide_index=True, width="stretch")
                st.caption("%d of %d rows. Highlighted rows are the ones the "
                           "finding is about." % (len(show), len(t)))
            with st.expander("Evidence and execution log"):
                st.markdown("**Evidence from the scan**")
                st.write(f.evidence)
                st.markdown("**Code that produced the chart and table**")
                st.code(ev.code or "(no chart for this check)",
                        language="python")
                st.caption("Check: %s. Every number on this page was counted by "
                           "code, not by a model." % f.found_by)
                run = st.session_state.get("xlog_" + f.key)
                if run:
                    show_steps(run)

    # ---- draft explanation -----------------------------------------------
    with right:
        with st.container(border=True):
            st.markdown("<div class='panel-h'>Draft explanation for review</div>",
                        unsafe_allow_html=True)
            docs, past = explore.related(f, folder)
            secs = explore.draft_explanation(f, ev, done.get(f.key), docs)
            icons = ["📈", "📊", "📄", "📘", "⚠️"]
            editing = st.session_state.get("edit_" + f.key, False)
            if expl.get("text") and not editing:
                secs = explore.split_sections(expl["text"])
            if not editing:
                for i, (h, txt) in enumerate(secs):
                    ic = "⚠️" if "observation" in h.lower() else \
                        "📘" if "document" in h.lower() else icons[min(i, 2)]
                    st.markdown("<div class='sec%s'><div class='ic'>%s</div>"
                                "<div><h5>%s</h5><p>%s</p></div></div>"
                                % (" warn" if ic == "⚠️" else "", ic, h, txt),
                                unsafe_allow_html=True)
            if editing:
                start = expl.get("text") or "\n\n".join(
                    "**%s**\n%s" % (h, t) for h, t in secs)
                new = st.text_area("Explanation", start, height=420,
                                   label_visibility="collapsed")
                s1, s2 = st.columns(2)
                if s1.button("Save draft", type="primary", width="stretch"):
                    save_explanation(folder, f.key, new, "draft", "reviewer",
                                     "edited", ai=False)
                    st.session_state["edit_" + f.key] = False
                    st.rerun()
                if s2.button("Cancel", width="stretch"):
                    st.session_state["edit_" + f.key] = False
                    st.rerun()
            st.markdown("<div class='foot'>Source: %s. Wording drafted by %s; "
                        "a reviewer must approve it.</div>"
                        % (", ".join(ev.datasets) or f.output_file,
                           "the AI" if expl.get("ai") else "code"),
                        unsafe_allow_html=True)
            if not editing:
                status = expl.get("status", "draft")
                b1, b2 = st.columns(2)
                if b1.button("Edit explanation", width="stretch",
                             disabled=status == "approved"):
                    st.session_state["edit_" + f.key] = True
                    st.rerun()
                if status in ("draft", "sent_back"):
                    if b2.button("Submit for review", type="primary",
                                 width="stretch"):
                        text = expl.get("text") or "\n\n".join(
                            "**%s**\n%s" % (h, t) for h, t in secs)
                        save_explanation(folder, f.key, text, "submitted",
                                         "reviewer", "submitted")
                        st.rerun()
                elif status == "submitted":
                    if b2.button("Approve", type="primary", width="stretch"):
                        save_explanation(folder, f.key, status="approved",
                                         note="approved")
                        st.rerun()
                    if st.button("Send back", width="stretch"):
                        save_explanation(folder, f.key, status="sent_back",
                                         note="sent back")
                        st.rerun()
                else:
                    b2.success("Approved")
                if live() and use_model and status != "approved":
                    if st.button("Draft the wording with AI", width="stretch"):
                        with st.spinner("Drafting..."):
                            run = get_agent().chat(
                                "Write the explanation for finding %s for a "
                                "reviewer, in four short parts with these "
                                "bold headings: How to read the figure, What "
                                "the data shows, Why it matters, Observation "
                                "for review. Use only these facts: %s %s %s"
                                % (f.key, ev.how_to_read, " ".join(ev.facts),
                                   f.what_is_wrong))
                        if run.ok:
                            save_explanation(folder, f.key, run.answer,
                                             "draft", "AI agent", "AI draft",
                                             ai=True)
                        else:
                            st.warning(run.answer)
                        st.session_state["xlog_" + f.key] = run
                        st.rerun()
            if docs or past:
                with st.expander("Sources from the documents (%d)"
                                 % (len(docs) + len(past))):
                    for h in docs:
                        st.markdown("**%s**" % h.cite)
                        st.caption(h.chunk.text[:500])
                    for h in past:
                        st.markdown("**Seen in a past review** · %s" % h.cite)
                        st.caption(h.chunk.text[:400])
            hist = expl.get("history", [])
            if hist:
                with st.expander("Audit trail (%d)" % len(hist)):
                    for h in reversed(hist):
                        st.caption("%s · %s · %s %s" % (h["at"], h["by"],
                                                        h["status"], h["note"]))
    st.markdown("<div class='foot'>Code supplies every number. The AI drafts "
                "wording only. A reviewer approves before anything leaves "
                "the team.</div>", unsafe_allow_html=True)


# ================================================================ Agent
elif page == "Agent":
    st.header("Agent")
    if not res:
        need_scan()
    if live() and use_model:
        st.markdown("<div class='engine' style='background:#e8f3ee'>🤖 <b>AI "
                    "agent</b> · %s %s. It chooses its own tools, checks the "
                    "data, and records what it finds. Subject IDs are sent as "
                    "codes only.</div>" % (current_mode(),
                                           agent_model(current_mode())),
                    unsafe_allow_html=True)
    else:
        st.markdown("<div class='engine' style='background:#f3f1ea'>⚙️ <b>"
                    "Offline agent</b>, no API key. It runs the same tools in "
                    "a fixed order for each kind of finding, and drafts fixes "
                    "and queries from templates. Put a key in <code>.env"
                    "</code> and restart to switch on the AI agent.</div>",
                    unsafe_allow_html=True)
    ag = get_agent()

    t1, t2, t3, t4 = st.tabs(["Run on findings", "Chat with the study",
                              "Fixes and queries", "Knowledge (RAG)"])

    with t1:
        a, b = st.columns(2)
        scope = a.selectbox("Which findings", [
            "To check only", "Critical only", "Critical and Major",
            "One layer", "All"])
        layer = a.selectbox("Layer", LAYERS) if scope == "One layer" else None
        jobs_l = b.multiselect("Jobs", ["Investigate", "Suggest fix",
                                        "Draft query"],
                               default=["Investigate", "Suggest fix",
                                        "Draft query"])
        jobs = tuple({"Investigate": "investigate", "Suggest fix": "fix",
                      "Draft query": "query"}[j] for j in jobs_l)
        pick = {
            "To check only": [f for f in res.findings
                              if f.confidence == "candidate"],
            "Critical only": [f for f in res.findings
                              if f.severity == "Critical"],
            "Critical and Major": [f for f in res.findings
                                   if f.severity in ("Critical", "Major")],
            "One layer": [f for f in res.findings if f.layer == layer],
            "All": list(res.findings)}[scope]
        st.caption("%d finding(s) selected.%s" % (
            len(pick), " Each one is a separate agent run, up to 10 tool "
            "calls." if live() and use_model else " Offline: under a second."))
        if st.button("Run agent", type="primary", disabled=not (pick and jobs)):
            bar = st.progress(0.0)
            runs = ag.work_many(pick, jobs, progress=lambda i, n, f: bar.progress(
                i / n, text="%d of %d: %s" % (i, n, f.finding[:70])))
            st.session_state.batch = runs
            st.rerun()
        runs = st.session_state.get("batch")
        if runs:
            tok = sum(r.tokens_in + r.tokens_out for _, r in runs)
            st.success("Agent finished %d finding(s)%s. Open Fixes and queries, "
                       "or the Findings page." % (
                           len(runs), ", %d tokens" % tok if tok else ""))
            st.dataframe([{"Finding": f.finding, "Layer": f.layer,
                           "Steps": len(r.steps), "Result": r.answer[:140]}
                          for f, r in runs], hide_index=True, width="stretch")

    with t2:
        st.caption("Ask anything about the study. "
                   + ("The agent decides which tools to use." if live() and
                      use_model else "Offline, it understands plain "
                      "questions: 'overview', 'how many subjects in ADSL', "
                      "'compare ADSL and EX', 'describe ADVS', 'show Table "
                      "12-5', 'what does the SAP say about populations', "
                      "'how is baseline defined', 'list critical findings'."))
        chat = st.session_state.setdefault("chat", [])
        for q, run in chat:
            with st.chat_message("user"):
                st.write(q)
            with st.chat_message("assistant"):
                if run.ok and live() and use_model:
                    st.markdown(run.answer)
                elif run.ok:
                    st.code(run.answer, language=None, wrap_lines=True)
                else:
                    st.warning(run.answer)
                show_steps(run)
        q = st.chat_input("Ask about the study, a dataset, an output, a finding")
        if q:
            with st.spinner("Agent working..."):
                run = ag.chat(q, history=[(x, r.answer) for x, r in chat])
            chat.append((q, run))
            st.rerun()

    with t3:
        done = agent_results(folder)
        by_key = {f.key: f for f in res.findings}
        rows = [(by_key[k], e) for k, e in done.items() if k in by_key]
        if not rows:
            st.info("Nothing yet. Run the agent on some findings first.")
        else:
            path = os.path.join("out", "%s_scan.xlsx" % study)
            write_scan_workbook(res, path, NOT_CHECKED, agent=done)
            with open(path, "rb") as fh:
                st.download_button("⬇ Excel with Agent Fixes and Queries tabs",
                                   fh.read(), file_name=os.path.basename(path))
            v = pd.Series([VERDICT[e["verdict"]][0] for _, e in rows
                           if e.get("verdict")]).value_counts()
            c = st.columns(4)
            tile(c[0], len(rows), "findings worked")
            for col, lab in zip(c[1:], ["Confirmed", "Needs a person",
                                        "Likely false alarm"]):
                tile(col, int(v.get(lab, 0)), lab.lower())
            kind = st.radio("Show", ["Fixes", "Queries"], horizontal=True)
            to = None
            if kind == "Queries":
                to = st.multiselect("To", ["site", "data_management",
                                           "sponsor", "programmer"],
                                    default=["site", "data_management",
                                             "sponsor", "programmer"])
            for f, e in sorted(rows, key=lambda r: (viz.SEV.index(r[0].severity),
                                                    r[0].layer)):
                items = e.get("fixes" if kind == "Fixes" else "queries", [])
                if kind == "Queries":
                    items = [q for q in items if q["to"] in to]
                if not items:
                    continue
                with st.container(border=True):
                    st.markdown("<span class='sev' style='background:%s'>%s"
                                "</span><span class='tag'>%s</span> <b>%s</b>"
                                % (SEV_COLOUR[f.severity], f.severity, f.layer,
                                   f.finding), unsafe_allow_html=True)
                    for x in items:
                        if kind == "Fixes":
                            st.caption(x["kind"].upper())
                            st.code(x["text"], language="sas"
                                    if x["kind"] == "sas" else None)
                        else:
                            st.caption("To %s · %s" % (
                                x["to"].replace("_", " "), x["subject"]))
                            st.code(x["text"], language=None, wrap_lines=True)

    with t4:
        from cra import rag
        idx = rag.index_for(folder)
        st.caption("The agent searches these documents and cites the section "
                   "it used. Plain keyword ranking (BM25): offline, no tokens. "
                   "It finds text; it never counts. Numbers still come from "
                   "the data.")
        by = rag.stats(idx)
        st.dataframe([{"Where": k[0], "Document": k[1], "Passages": n}
                      for k, n in sorted(by.items())],
                     hide_index=True, width="stretch")
        a, b = st.columns([3, 2])
        with a:
            st.markdown("**Search the documents**")
            q = st.text_input("Search", placeholder="how is baseline defined",
                              label_visibility="collapsed")
            where = st.radio("In", ["all", "sap", "specs", "shells", "library"],
                             horizontal=True)
            if q:
                for h in idx.search(q, 5, None if where == "all" else {where}):
                    with st.container(border=True):
                        st.markdown("**%s** · score %.1f" % (h.cite, h.score))
                        st.write(h.chunk.text[:700])
        with b:
            st.markdown("**Reference library** (shared by every study)")
            st.caption("Past review sheets, CDISC Controlled Terminology from "
                       "NCI, guidance your company may use. .xlsx .csv .docx "
                       ".pdf .txt")
            lib = st.file_uploader("Add to library", accept_multiple_files=True,
                                   type=["xlsx", "xls", "csv", "docx", "pdf",
                                         "txt", "md"],
                                   label_visibility="collapsed",
                                   key="lib%d" % st.session_state.get("ver", 0))
            if lib and st.button("Add to library"):
                os.makedirs(rag.LIBRARY, exist_ok=True)
                for fl in lib:
                    with open(os.path.join(rag.LIBRARY,
                                           os.path.basename(fl.name)), "wb") as fh:
                        fh.write(fl.getvalue())
                bump()
                st.rerun()
            if os.path.isdir(rag.LIBRARY):
                for name in sorted(os.listdir(rag.LIBRARY)):
                    st.caption("📚 " + name)

        st.divider()
        st.markdown("**SAP rules, read from the SAP**")
        st.caption("Found in the SAP and protocol by pattern, each with the "
                   "passage it came from. Tick the ones that are right and "
                   "save: they go into sap/spec.txt, which the checks use.")
        sugg = rag.suggest_rules(folder)
        current = stdy_rules = study_obj(study).rules
        if not sugg:
            st.info("No rules found. Upload the SAP or protocol on the "
                    "Overview page.")
        else:
            picks = {}
            for k, v in sugg.items():
                c1, c2 = st.columns([1, 3])
                now = current.get(k)
                same = now is not None and now.replace(" ", "") == \
                    v["value"].replace(" ", "")
                picks[k] = c1.checkbox("%s = %s" % (k, v["value"]),
                                       value=not now, key="rule_" + k)
                c2.caption("%s · “…%s…”%s" % (
                    v["cite"], v["quote"],
                    "" if now is None else (" · spec.txt already has this"
                                            if same else " · spec.txt has %s"
                                            % now)))
            if st.button("Save ticked rules to spec.txt", type="primary"):
                rag.write_rules(folder, {k: sugg[k]["value"]
                                         for k, on in picks.items() if on})
                bump()
                st.toast("Saved. Run the scan again to use them.")
                st.rerun()


# ================================================================ Visualize
elif page == "Visualize":
    st.header("Visualize")
    if not res:
        need_scan()
    if not res.findings:
        st.success("No findings to chart.")
        st.stop()
    df = viz.frame(res.findings, status_of)
    done = agent_results(folder)
    c = st.columns(5)
    tile(c[0], len(df), "findings")
    tile(c[1], int((df.Severity == "Critical").sum()), "critical")
    tile(c[2], int((df.Status == "To check").sum()), "to check")
    tile(c[3], "%d%%" % round(100 * sum(1 for f in res.findings
                                         if f.key in done) / len(df)),
         "worked by the agent")
    tile(c[4], totals(res.tlf_compare)["changed"] if res.tlf_compare else "—",
         "TLF outputs changed since last delivery")

    def table(t):
        with st.expander("Show as table"):
            st.dataframe(t, hide_index=True, width="stretch")

    st.subheader("Findings by layer and severity")
    st.altair_chart(viz.by_layer(df, LAYERS), width="stretch", theme=None)
    table(df.pivot_table(index="Layer", columns="Severity", values="Finding",
                         aggfunc="count", fill_value=0).reset_index())

    a, b = st.columns(2)
    with a:
        st.subheader("Where they cluster")
        st.caption("Layer against review area. Darker means more findings.")
        st.altair_chart(viz.heatmap(df, LAYERS), width="stretch", theme=None)
    with b:
        st.subheader("Files and datasets with most findings")
        ch, t = viz.top_files(df)
        st.altair_chart(ch, width="stretch", theme=None)
        table(t.rename(columns={"Where": "File or dataset", "n": "Findings"}))

    a, b = st.columns(2)
    with a:
        st.subheader("Review status")
        t = df.Status.value_counts().reset_index()
        t.columns = ["Status", "Findings"]
        st.altair_chart(viz.simple_bars(t, "Status", "Findings", "Findings"),
                        width="stretch", theme=None)
    with b:
        st.subheader("Agent verdicts")
        v = [VERDICT[e["verdict"]][0] for k, e in done.items()
             if e.get("verdict") and k in {f.key for f in res.findings}]
        if v:
            t = pd.Series(v).value_counts().reset_index()
            t.columns = ["Verdict", "Findings"]
            st.altair_chart(viz.simple_bars(t, "Verdict", "Findings",
                                            "Findings"), width="stretch", theme=None)
        else:
            st.caption("The agent has not worked any findings yet.")

    if res.tlf_compare:
        a, b = st.columns(2)
        tt = totals(res.tlf_compare)
        with a:
            st.subheader("TLF outputs since the last delivery")
            t = pd.DataFrame({"Status": ["Changed", "New", "Removed",
                                         "Unchanged"],
                              "Outputs": [tt["changed"], tt["new"],
                                          tt["removed"], tt["same"]]})
            st.altair_chart(viz.simple_bars(t, "Status", "Outputs", "Outputs",
                                            sort=None), width="stretch", theme=None)
        with b:
            st.subheader("What changed in them")
            kinds = {}
            for d in res.tlf_compare:
                for k, n in d.counts().items():
                    kinds[k] = kinds.get(k, 0) + n
            if kinds:
                t = pd.DataFrame({"Change": list(kinds),
                                  "Count": list(kinds.values())})
                st.altair_chart(viz.simple_bars(t, "Change", "Count",
                                                "Changes"), width="stretch", theme=None)

    hist = load_history(folder)
    st.subheader("Findings over time")
    if len(hist) >= 2:
        ch, t = viz.trend(hist)
        st.altair_chart(ch, width="stretch", theme=None)
        table(t.pivot_table(index="Scan", columns="Severity",
                            values="Findings").reset_index())
    else:
        st.caption("Shown once the study has been scanned at least twice. "
                   "Each scan is kept, so you can watch the count fall as "
                   "findings are fixed.")
