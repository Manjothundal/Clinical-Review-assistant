# Clinical Review Assistant

Reviews a delivery of TLF outputs and writes a findings sheet in the five
columns the team already uses:

    Area | Finding | Output / File | What is wrong | Evidence

Version 2. Version 1 read datasets only. This version reads the delivered RTF
outputs as well, which is where almost every real finding lives.

## Start here

    pip install -r requirements.txt
    python make_sample_study.py         builds a full demo study with problems planted
    streamlit run app.py

Open **Overview**, press **Run scan**, then open **Findings**.

## The scan (version 3)

One upload box takes everything for a study. Each file is sorted by its name,
and you can change the guess before adding it. A zip works too.

| Upload | Goes to | What it switches on |
|---|---|---|
| raw EDC extracts (.csv .xpt .sas7bdat) | Raw Data | lost subjects and records, bad dates, text in numeric fields, duplicates |
| SDTM datasets | SDTM | subjects not in DM, study days, STRESN, DM arm vs EX |
| ADaM datasets | ADaM | ADSL vs DM, SAFFL vs dosing, TRTSDT, BASE and CHG re-derived |
| TLF outputs (.rtf) | TLF | every output check, plus output Ns against ADaM |
| SAP (.docx .pdf .txt) and spec.txt | SAP | populations, N, treatments, PK parameters, planned outputs |
| mock shells (.docx .pdf .rtf or shells.txt) | Mock Shells | not delivered, no shell, title wording |
| specs (.xlsx .csv with Dataset and Variable columns) | SDTM / ADaM | variables, labels and types against the data |

CDISC checks (required variables, name and label lengths, ISO 8601 dates,
--SEQ, DOMAIN, PARAM to PARAMCD, Y/N flags, a small subset of Controlled
Terminology) run on whatever SDTM and ADaM was uploaded, and land on their own
CDISC tab.

The Excel sheet has a Summary tab, an All Findings tab, then one tab per layer:
Raw Data, SDTM, ADaM, TLF, SAP, CDISC, Mock Shells. Every tab keeps the five
review columns, plus Severity and Status.

- **Confirmed**: code proved it.
- **To check**: code noticed it but cannot prove it on its own.
- **Kept / Rejected**: a person decided, on the Findings page. Decisions are
  saved in the study folder (`decisions.json`), so a rejected finding does not
  come back on the next scan.

Without the screen:

    python run_review.py --no-model      the older TLF-only review

## The agent

The **Agent** page does four jobs, on one finding or on many at once:

| Job | What it does |
|---|---|
| Investigate | re-checks the finding with its tools and records a verdict: confirmed, needs a person, or likely false alarm |
| Suggest fix | writes the SAS fix (or the footnote, title or spec change) using the real dataset and variable names |
| Draft query | writes the query to the site, data management, the sponsor or the programmer |
| Chat | answers questions about the study: "why is T3 n=24 on Table 14-3?" |

Its tools only read. It cannot change a dataset or an output, and it cannot
reject a finding: only a person can. Every step it took is shown under its
answer. Fixes and queries are on the Findings cards and on two extra Excel
tabs, **Agent Fixes** and **Queries**.

**No API key:** the offline agent runs the same tools in a fixed order for
each kind of finding, and fills SAS fixes and queries from templates. Chat
answers plain questions ("how many subjects in ADSL", "compare ADSL and EX",
"show Table 12-5").

**With a key** in `.env` (CRA_MODEL_MODE=anthropic or openai, CRA_API_KEY=...)
the AI agent chooses its own tools, up to 10 calls per task. Rules held in code,
not in the prompt:

- subject IDs are replaced by codes (S001, S002 ...) before anything is sent,
  and shown as real IDs again on your screen. Birth dates, initials and
  investigator names are never sent.
- filters go through a small safe language, never `eval`, so nothing the model
  writes can run as code
- an answer with a number that no tool returned is withheld
- tool results are cut at 2,500 characters, the tool list and instructions are
  cached, and a run stops after 10 tool rounds

## Explore a finding

Open any finding with the **Explore** button on its card. One page, three
panels:

| Panel | What is on it |
|---|---|
| Conversation | ask about this finding: why it matters, how to confirm it, draft a fix, or your own question |
| Graph and Data used | a chart that redoes the check from the data, flagged records in orange and the rest in grey; the records behind it, flagged rows highlighted; switch to Raw, SDTM or ADaM to see the flagged subjects in any dataset; the evidence and the code that drew it |
| Draft explanation for review | how to read the figure, what the data shows, why it matters, what to review. Edit it, submit it, then approve or send it back. Every step is kept in an audit trail. |

Charts by check: CHG against AVAL minus BASE, ADSL against DM, TRTSDT against
the first dose, safety flag against dosing (2 x 2), subjects in one dataset
and not another, raw against SDTM records per subject, values outside CDISC
terminology, dates and numbers that cannot be read, study days, output Ns
against ADaM, population sizes, and counts down an output. Findings about
text (titles, specs, required variables) show their table instead.

Code draws every chart and counts every number. With a key, the AI may draft
the wording of the explanation, under the same number rule, and a reviewer
still approves it.

## RAG: the documents, searched

The agent and the Explore page search the study's documents and quote the
section they used, for example `[DEMO-BE-101_SAP.docx §8.1 Baseline]`.

| Searched | From |
|---|---|
| SAP and protocol | `sap/` (.docx, .pdf, .txt) |
| Mock shells | `shells/` |
| Specs | `specs/` (one passage per variable row) |
| Reference library | `library/` beside the app, shared by every study: past review sheets, CDISC Controlled Terminology from NCI, guidance you may use |

How it works, all in `cra/rag.py`:

- documents are cut along their numbered sections ("8.2 Missing Data"), long
  sections into overlapping windows, spreadsheet rows one per passage
- BM25 keyword ranking, with a few clinical synonyms (baseline and pre-dose,
  AE and adverse event). Plain Python: offline, no package, no tokens
- each check has a short topic to look up (CHG looks up the baseline rules,
  a missing denominator looks up how percentages are based), so the SAP
  passage shown on Explore is the rule behind the finding
- a past review row that names the same check is linked exactly; otherwise a
  past finding is shown only on a very strong match

**SAP rules read from the SAP.** Agent → Knowledge finds the rules the checks
need (population size, treatments, PK parameters, significant digits,
crossover) in the SAP text, each with the passage it came from. Tick the
right ones and save; they go into `sap/spec.txt`. On the demo it finds all five
rules that were typed into spec.txt by hand.

It finds text; it never counts. Numbers still come only from the data checks.

## Old vs new TLF

On the Overview page, add the previous delivery's RTF files (or name them with
`old` / `prev`, or put them in a `tlf_old/` folder in a zip). The app matches
each output by file name or number and lists what changed: titles, column
headers, footnotes, every table cell, rows added or removed, and the program on
the Source line. A new run date on its own is not counted. The comparison is
also a **TLF Compare** tab in the Excel sheet.

## Visualize

Charts of the findings: by layer and severity, where they cluster (layer
against area), the files and datasets with most findings, review status, agent
verdicts, what changed since the last TLF delivery, and the trend across scans.
Every chart can be shown as a table.

## Tokens

The model is optional. When it is on:

- only the **To check** items are sent. Confirmed findings keep the code's
  wording. On the demo study that is 8 items instead of 67, about 600 tokens
  instead of about 6,500.
- the items are sent as compact JSON with short keys
- every answer is saved in `out/.cache`, so running the same scan again costs
  nothing
- the instructions are marked for prompt caching on Anthropic
- the default models are the cheap ones: gpt-4.1-mini and claude-haiku-4-5

## The one rule that shapes everything

**Code produces every number. The model only chooses words.**

The model is given the check name, the file name and the counts code already
worked out. It never sees a patient record, and it never sees the body of an
output. Any number it writes that is not already in the Evidence column causes
its wording to be thrown away and the code's own wording used instead. That rule
is in `cra/review.py`, not in the prompt, because a prompt is a request and this
has to be a guarantee.

`tests/test_privacy.py` fails the build if that changes.

## Where the checks came from

Every check is written from a real finding on a real review sheet. The mapping
is in `docs/findings_map.csv`: 38 findings from study AQ109109, each one tied to
the check that should catch it.

Run the scorecard at any time:

    python docs/score.py

Today it reports 30 of 38 with a check written, 25 of 38 reproduced on the
sample delivery. When you add a check, this number moves. When you break one, it
moves the other way.

## Asking about a finding

Every finding on the Review page has an **Ask about this finding** panel. Four
buttons for the usual questions, or type your own.

What it is allowed to read is decided in one file, `cra/context.py`, and shown
on screen under every answer:

| Level | What goes to the model |
|---|---|
| `summary` (default) | The finding and its evidence, the output's titles, column names and footnotes, the SAP rules in `spec.txt`, and the other findings on the same file. **No table rows.** |
| `table` | The above plus the body rows, with any Subject, Site or Investigator column replaced by `(id)`. Turned on per question, with a tick box. |
| never | A dataset record, a subject identifier, or any file from the study folder. There is no level that includes these. |

Two things the answer cannot do, both enforced in code rather than asked for in
the prompt:

- **It cannot state a number it was not given.** The answer is thrown away and
  you are told which number was invented.
- **It cannot clear a finding.** An answer that says the finding is fine or
  needs no action is thrown away. Only a person decides that, with Keep and
  Reject.

With the model off it still answers, by repeating the evidence and saying the
model is off. It never pretends to explain.

## The three engines

1. **Plain code.** Reads the outputs and the data. Produces exact counts.
   No AI. 30 of the 38 real findings need nothing more than this.
2. **Judgement.** Decides keep or drop for the handful of things code notices
   but cannot prove, and writes the wording. 5 of the 38.
3. **A person.** Keeps or rejects each finding in the app. A rejected finding
   does not come back next run, because the key is stable.

## Confidence

Every flag is `certain` or `candidate`.

- **certain** - code proved it. It goes on the Findings tab.
- **candidate** - code noticed something that is sometimes fine. It goes to the
  model. With the model off it goes to a separate "To look at" tab, so the
  Findings tab stays something a reviewer can trust.

## The files

    make_sample_study.py     full demo study for the scan, with the answer key
    make_sample_data.py      demo datasets, with problems planted in them
    make_sample_outputs.py   demo RTF outputs, with problems planted in them
    run_review.py            one review from the command line
    app.py                   the screen. no logic in here

    cra/rtf.py               reads one RTF output into titles, rows, footnotes
    cra/outputs.py           reads a whole delivery, plus shells.txt and spec.txt
    cra/flags.py             the shared Flag shape, and merging duplicates
    cra/checks_output.py     checks that read one output on its own
    cra/checks_across.py     checks that need several outputs together
    cra/scan.py              checks that read the datasets
    cra/pipeline.py          one review, start to finish
    cra/review.py            the model layer, and the number rule
    cra/findings.py          a finding, the stable key, the five columns
    cra/excel_out.py         writes the sheet
    cra/model.py             mock, openai or anthropic. mock needs no key
    cra/profile.py           the only view of the data a model ever gets
    cra/codegen.py           R output. not written yet, see below
    cra/study.py             a study folder: upload sorting and reading every file type
    cra/checks_layers.py     raw, SDTM, ADaM, CDISC, SAP, shells, TLF vs ADaM
    cra/scan_study.py        one full scan, and saved Keep / Reject decisions
    cra/compare_tlf.py       old TLF delivery against new
    cra/viz.py               the charts on the Visualize page
    cra/explore.py           the chart, data and draft explanation for one finding
    cra/rag.py               document search with citations, SAP rule reading
    library/                 shared reference documents (past reviews, CT)
    cra/agent/where.py       the safe filter language
    cra/agent/tools.py       the agent's tools, subject ID codes, agent.json
    cra/agent/loop.py        the tool loop, Anthropic and OpenAI, number rule
    cra/agent/playbooks.py   the offline agent: SAS and query templates
    cra/agent/tasks.py       investigate, fix, query, chat

    studies/DEMO-BE-101/     raw/ sdtm/ adam/ tlf/ tlf_old/ sap/ shells/ specs/

    outputs/DEMO-BE-101/     the demo delivery
        shells.txt           what the mock shells require
        spec.txt             the few SAP rules a check may rely on

## What it does NOT do

Written on the Read me tab of every sheet, because a reviewer who cannot see
the gaps will assume there are none.

- The SAP is read for population names and output numbers. Detailed rules
  still come from `spec.txt`, copied out by hand.
- Only a small subset of CDISC Controlled Terminology. No MedDRA, no WHODrug.
- No define.xml, ADRG or cSDRG.
- A figure is read for its titles and footnotes. Never for the picture.
- RTF only. No Word, no PDF.

## What comes next, in order

1. The 8 remaining checks from `docs/score.py`.
2. **R.** `cra/codegen.py` is a stub. The plan is Tplyr and r2rtf for the
   output, haven for the data, diffdf for the comparison, renv for the versions.
3. Read the SAP itself, so `spec.txt` is no longer written by hand.
4. CDISC controlled terminology and MedDRA.
5. Learned checks: a rule taken from your own finished studies, tested against
   the whole programme before it is turned on.

## Turning the model on, later

You do not need this to use the app. `--no-model` produces the whole sheet with
no key at all, and the tests always run with no key.

When you do have one:

    copy .env.example .env

The app reads `.env` itself. No extra package is needed.

Put the key in it, set `CRA_MODEL_MODE`, and in the app turn on "Use the model
for wording". Four settings are supported.

| Mode | When to use it |
|---|---|
| `mock` | No key. Keeps what code proved, drops most candidates. The default. |
| `openai` | An OpenAI key. Set `CRA_API_BASE` too if the company uses Azure. |
| `anthropic` | An Anthropic key. |
| `paste` | No API at all, only the ChatGPT website. The app writes the prompt to `out/prompt_to_paste.txt`, you paste it into ChatGPT, save the reply into `out/answer_from_chatgpt.txt`, and run again. |

Paste mode exists so you can see exactly what would be sent before anything
leaves the company. Open the file and read it. It holds check names, output file
names and counts. No patient record, and no contents of any study output.

### The coding assistant is a different thing

ChatGPT or Copilot inside VS Code helps *you* write code. It has nothing to do
with the settings above and it is not involved when the app runs. Use it freely
for the code. Do not paste study data into it.
