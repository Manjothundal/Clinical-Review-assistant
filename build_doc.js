// Builds START_HERE.docx - the instruction document for the project.
//   node build_doc.js
const fs = require("fs");
const d = require("docx");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  LevelFormat, PageBreak, convertInchesToTwip,
} = d;

const NAVY = "17336E";
const GREY = "5A6B7B";
const RULE = { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
               left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } };

// One numbering reference per list, so numbering restarts in every section.
const refs = [];
for (let i = 1; i <= 12; i++) refs.push("n" + i);
const numbering = {
  config: refs.map((ref) => ({
    reference: ref,
    levels: [{
      level: 0, format: LevelFormat.DECIMAL, text: "%1.",
      alignment: AlignmentType.START,
      style: { paragraph: { indent: { left: 460, hanging: 260 } } },
    }],
  })).concat([{
    reference: "bullets",
    levels: [{
      level: 0, format: LevelFormat.BULLET, text: "•",
      alignment: AlignmentType.START,
      style: { paragraph: { indent: { left: 460, hanging: 260 } } },
    }],
  }]),
};

const P = (text, opts = {}) => new Paragraph({
  spacing: { after: opts.after === undefined ? 140 : opts.after },
  alignment: opts.align,
  children: [new TextRun({
    text, bold: opts.bold, italics: opts.italic, size: opts.size || 21,
    color: opts.color, font: "Calibri",
  })],
});

const H1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 160 },
  children: [new TextRun({ text, bold: true, size: 30, color: NAVY, font: "Calibri" })],
});

const H2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2, spacing: { before: 260, after: 120 },
  children: [new TextRun({ text, bold: true, size: 24, color: NAVY, font: "Calibri" })],
});

const NUM = (text, ref) => new Paragraph({
  numbering: { reference: ref, level: 0 }, spacing: { after: 90 },
  children: [new TextRun({ text, size: 21, font: "Calibri" })],
});

const BUL = (text) => new Paragraph({
  numbering: { reference: "bullets", level: 0 }, spacing: { after: 90 },
  children: [new TextRun({ text, size: 21, font: "Calibri" })],
});

const CODE = (lines) => new Paragraph({
  spacing: { before: 100, after: 140 },
  shading: { type: ShadingType.CLEAR, fill: "F2F5F9" },
  children: lines.flatMap((l, i) => {
    const runs = [];
    if (i > 0) runs.push(new TextRun({ break: 1 }));
    runs.push(new TextRun({ text: "  " + l, font: "Consolas", size: 19 }));
    return runs;
  }),
});

const NOTE = (text) => new Paragraph({
  spacing: { before: 120, after: 160 },
  shading: { type: ShadingType.CLEAR, fill: "FFF6E0" },
  border: { left: { style: BorderStyle.SINGLE, size: 18, color: "F5C242" } },
  indent: { left: 160 },
  children: [new TextRun({ text: "  " + text, size: 21, font: "Calibri" })],
});

// Table with dual widths: columnWidths on the table AND width on every cell.
function table(rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    columnWidths: widths,
    width: { size: total, type: WidthType.DXA },
    rows: rows.map((cells, r) => new TableRow({
      children: cells.map((text, c) => new TableCell({
        width: { size: widths[c], type: WidthType.DXA },
        shading: r === 0 ? { type: ShadingType.CLEAR, fill: NAVY }
                         : (r % 2 === 0 ? { type: ShadingType.CLEAR, fill: "F2F5F9" }
                                        : undefined),
        margins: { top: 80, bottom: 80, left: 110, right: 110 },
        children: [new Paragraph({
          spacing: { after: 0 },
          children: [new TextRun({
            text, size: 19, bold: r === 0,
            color: r === 0 ? "FFFFFF" : undefined,
            font: c === 0 && r > 0 ? "Consolas" : "Calibri",
          })],
        })],
      })),
    })),
  });
}

const children = [];

// ---------------------------------------------------------------- cover
children.push(new Paragraph({ spacing: { before: 1800, after: 0 },
  children: [new TextRun({ text: "Clinical Review Assistant", bold: true,
                           size: 52, color: NAVY, font: "Calibri" })] }));
children.push(P("Version 2  -  reviewing the outputs, not just the data",
                { size: 26, color: GREY, after: 900 }));
children.push(P("How to open it, how to run it, and how to add your own check.",
                { size: 23, after: 120 }));
children.push(P("Written so you can follow it without knowing any of it already.",
                { size: 23, color: GREY, after: 2400 }));
children.push(P("Manjot Kaur Hundal", { size: 21, color: GREY, after: 40 }));
children.push(P("29 September 2026", { size: 21, color: GREY }));
children.push(new Paragraph({ children: [new PageBreak()] }));

// ---------------------------------------------------------------- 1
children.push(H1("1.  What you are building"));
children.push(P("An app that reads a delivery of TLF outputs and writes a " +
  "findings sheet. The sheet has the same five columns as the one the team " +
  "fills in by hand today:"));
children.push(CODE(["Area | Finding | Output / File | What is wrong | Evidence"]));
children.push(P("Nothing about the sheet is new. What is new is that most of " +
  "it is filled in before a person opens it."));

children.push(H2("What changed in version 2"));
children.push(P("Version 1 read the datasets. That was the wrong place to " +
  "look. Almost every finding on a real review sheet is about an output file: " +
  "a title that does not match the numbers under it, a footnote that belongs " +
  "to a different table, a figure that declares a subject count the table " +
  "beside it contradicts."));
children.push(P("So version 2 reads the delivered RTF outputs as well, and " +
  "the biggest new family of checks is the one that only works when you read " +
  "several outputs together."));

children.push(H2("Where the checks come from"));
children.push(P("Every check in this project was written from a real finding " +
  "on a real review sheet. Thirty-eight findings from study AQ109109 are " +
  "listed in docs/findings_map.csv, each one tied to the check that should " +
  "catch it."));
children.push(NOTE("This is the part that matters. The app is not trying to " +
  "be clever. It is trying to reproduce a standard that already exists."));
children.push(P("You can measure it at any time:"));
children.push(CODE(["python docs/score.py"]));
children.push(P("Today that prints: 30 of 38 findings have a check written, " +
  "25 of 38 are reproduced on the sample delivery. When you add a check, the " +
  "number goes up. When you break one, it goes down."));

// ---------------------------------------------------------------- 2
children.push(H1("2.  Install the two things you need"));
children.push(H2("Python"));
children.push(NUM("Go to python.org, Downloads. Take the newest 3.x.", "n1"));
children.push(NUM("Run the installer. On the FIRST screen tick " +
  "\"Add python.exe to PATH\". This one tick saves an hour later.", "n1"));
children.push(NUM("Click Install Now and wait.", "n1"));
children.push(H2("Visual Studio Code"));
children.push(NUM("Go to code.visualstudio.com and download it.", "n2"));
children.push(NUM("Install it with all the default choices.", "n2"));
children.push(NUM("Open it. On the left there is a row of icons. Click the " +
  "one with four squares, which is Extensions.", "n2"));
children.push(NUM("Type Python in the search box. Install the one by " +
  "Microsoft.", "n2"));

// ---------------------------------------------------------------- 3
children.push(H1("3.  Open the project"));
children.push(NUM("Unzip clinical-review-assistant.zip somewhere you can " +
  "find again. Your Documents folder is fine.", "n3"));
children.push(NUM("In VS Code choose File, then Open Folder.", "n3"));
children.push(NUM("Pick the folder called cra. Not the folder above it, and " +
  "not a folder inside it.", "n3"));
children.push(NUM("You should now see app.py, README.md and a folder also " +
  "called cra in the list on the left.", "n3"));
children.push(NUM("Open a terminal: the Terminal menu, then New Terminal. A " +
  "black panel appears at the bottom. Everything below is typed there.", "n3"));

// ---------------------------------------------------------------- 4
children.push(H1("4.  Get it running"));
children.push(P("Four commands. Type them one at a time and wait for each to " +
  "finish."));
children.push(CODE([
  "pip install -r requirements.txt",
  "python make_sample_data.py",
  "python make_sample_outputs.py",
  "streamlit run app.py",
]));
children.push(P("The first one takes a few minutes. The next two take a " +
  "second each. The fourth opens a browser tab."));
children.push(NOTE("No API key is needed. Nothing here talks to the internet."));

children.push(H2("What each one did"));
children.push(table([
  ["Command", "What it did"],
  ["pip install", "Fetched the libraries the project uses."],
  ["make_sample_data.py", "Wrote three demo studies into data/, with problems planted on purpose."],
  ["make_sample_outputs.py", "Wrote twenty demo RTF outputs into outputs/DEMO-BE-101/, also with problems planted on purpose."],
  ["streamlit run app.py", "Started the screen."],
], [2600, 6200]));

// ---------------------------------------------------------------- 5
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(H1("5.  What you should see"));
children.push(P("Five pages down the left."));
children.push(table([
  ["Page", "What it is for"],
  ["Overview", "What is in the delivery, what ran, and what this run did NOT look at."],
  ["Outputs", "One output read back the way the checks see it. If it looks wrong here, the reader is wrong, not the check."],
  ["Review", "The findings, in the five columns. Keep or Reject each one. Then write the sheet."],
  ["To look at", "Things the code noticed but cannot prove. Not findings."],
  ["What the AI sees", "The exact text a model would be given. Read this one at least once."],
], [2100, 6700]));

children.push(H2("The Overview page, second half"));
children.push(P("Scroll down and you will find a list headed \"What this run " +
  "did NOT look at\". It says the app does not read the SAP, does not check " +
  "CDISC controlled terminology, does not read a picture."));
children.push(P("That list is deliberate. A reviewer who cannot see the gaps " +
  "will assume there are none, and that is how an app like this causes harm. " +
  "It is printed on the Read me tab of every sheet as well."));

// ---------------------------------------------------------------- 6
children.push(H1("6.  How a finding is made"));
children.push(P("Three steps. Each one can be checked by a person."));
children.push(table([
  ["Step", "What it does", "Can it invent a number?"],
  ["1  Code", "Reads the outputs and the data. Counts things. Produces the Evidence column.", "No"],
  ["2  Model", "Decides keep or drop for the few things code cannot prove. Writes the wording.", "No, see below"],
  ["3  Person", "Keeps or rejects each finding on the Review page.", "No"],
], [1400, 5100, 2300]));

children.push(H2("The rule that makes it safe"));
children.push(P("Every number in the wording the model writes must already " +
  "appear in the Evidence the code produced. If it does not, the wording is " +
  "thrown away and the code's own wording is used instead."));
children.push(P("That rule lives in cra/review.py, in the function " +
  "numbers_not_in_evidence. It is written in code, not in the prompt, " +
  "because a prompt is a request and this has to be a guarantee."));
children.push(NOTE("The model is never sent a patient record, and never sent " +
  "the body of an output. It gets the check name, the file name and the " +
  "counts. tests/test_privacy.py fails the build if that ever changes."));

children.push(H2("Certain and candidate"));
children.push(P("Every flag is one or the other."));
children.push(BUL("certain - code proved it. It goes on the Findings tab."));
children.push(BUL("candidate - code noticed something that is sometimes " +
  "perfectly fine. A summary table with no treatment columns, for example, " +
  "is sometimes wrong and sometimes on purpose. These go to the model. With " +
  "the model off they go to a separate tab called To look at."));
children.push(P("This is why the Findings tab stays something a reviewer can " +
  "trust. Nothing unproved is mixed in with it."));

// ---------------------------------------------------------------- 7
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(H1("7.  What each file does"));
children.push(table([
  ["File", "What it does"],
  ["cra/rtf.py", "Reads one RTF output into titles, column headers, body rows and footnotes."],
  ["cra/outputs.py", "Reads a whole delivery, plus shells.txt and spec.txt."],
  ["cra/flags.py", "The shared Flag shape. Also merges the same problem on three files into one finding."],
  ["cra/checks_output.py", "Checks that read one output on its own."],
  ["cra/checks_across.py", "Checks that need several outputs side by side."],
  ["cra/scan.py", "Checks that read the datasets."],
  ["cra/pipeline.py", "One review, start to finish."],
  ["cra/review.py", "The model layer, and the number rule."],
  ["cra/findings.py", "A finding, the stable key, the five columns."],
  ["cra/excel_out.py", "Writes the sheet."],
  ["cra/model.py", "mock, openai or anthropic. mock needs no key."],
  ["cra/codegen.py", "R output. A stub. This is piece two of the project."],
  ["app.py", "The screen. No logic in here at all."],
], [2700, 6100]));

children.push(H2("The two small text files"));
children.push(P("Inside outputs/DEMO-BE-101 there are two plain text files. " +
  "They are how the app knows things it cannot work out from the outputs."));
children.push(table([
  ["File", "What is in it"],
  ["shells.txt", "One line per output the mock shells require. This is how the app knows an output did not arrive."],
  ["spec.txt", "A handful of rules copied out of the SAP by hand: the population size, the number of significant digits allowed, the treatment names."],
], [1900, 6900]));
children.push(NOTE("Writing spec.txt by hand is a shortcut, and an honest " +
  "one. Reading the SAP itself is step three of what comes next. Until then, " +
  "a check that needs a SAP rule simply does not run, and the Overview page " +
  "says so."));

// ---------------------------------------------------------------- 8
children.push(H1("8.  Adding your own check"));
children.push(P("This is the part you will do most often. Here is the whole " +
  "thing, start to finish."));
children.push(NUM("Pick a real finding from your own review sheet. Not an " +
  "idea. A finding that actually happened.", "n4"));
children.push(NUM("Open cra/checks_output.py. Copy the shortest check in " +
  "there, which is program_has_path_and_version.", "n4"));
children.push(NUM("Change it. A check takes a Package and returns a list of " +
  "Flags. Nothing else.", "n4"));
children.push(NUM("Add its name to ALL_OUTPUT_CHECKS at the bottom of the " +
  "file, or it will never run.", "n4"));
children.push(NUM("Plant the problem in make_sample_outputs.py so you can " +
  "see it fire.", "n4"));
children.push(NUM("Write one test in tests/test_outputs.py. Name it after " +
  "the row of the review sheet it came from.", "n4"));
children.push(NUM("Run  python -m pytest tests/ -q  and then  python " +
  "docs/score.py  to see the number move.", "n4"));

children.push(H2("What a Flag has to carry"));
children.push(table([
  ["Field", "What goes in it"],
  ["kind", "The check name. Used for the stable key."],
  ["area", "PK, PD, OMAS, Safety-AE, Safety-Core, Safety-Lab, Human Factors or Cross-cutting."],
  ["output", "The file name. Several file names, comma separated, if it affects several."],
  ["finding", "One line. This is the Finding column on the sheet."],
  ["what_is_wrong", "Two to four sentences. Why a reader of the output would be misled."],
  ["evidence", "The numbers. Every one of them produced by your code, right here."],
  ["severity", "Critical, Major or Minor."],
  ["confidence", "certain if your code proved it. candidate if it might be fine."],
], [2000, 6800]));

children.push(NOTE("If you cannot fill in evidence with real numbers, the " +
  "check is not ready. A finding with no evidence is dropped before anyone " +
  "sees it, on purpose."));

// ---------------------------------------------------------------- 9
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(H1("9.  Two bugs worth knowing about"));
children.push(P("Both were found by the tests, and both are the kind of thing " +
  "that would have quietly ruined a real review."));
children.push(H2("The demographics table that was read as a figure"));
children.push(P("The code decided an output was a figure if the word graph " +
  "appeared in its name or title. The word Demographic contains the letters " +
  "of graph. So the demographics table was filed as a figure and every table " +
  "check skipped it, silently."));
children.push(P("The fix was to match whole words. The test that holds it " +
  "down is test_a_demographics_table_is_not_read_as_a_figure."));
children.push(H2("The count that was not a dip"));
children.push(P("A check looked for a subject count that falls and then " +
  "recovers, which is a real problem on a cumulative AUC table. On a lab " +
  "table the rows alternate Baseline and End of Study for different " +
  "parameters, so the count changes between parameters for perfectly good " +
  "reasons. The check flagged all of them."));
children.push(P("The fix was to only compare rows that belong to the same " +
  "series. Two rows belong together when their labels are the same once the " +
  "digits are removed."));
children.push(NOTE("A check that cries wolf is worse than no check. The " +
  "first reviewer who sees three false findings stops reading the sheet."));

// ---------------------------------------------------------------- 10
children.push(H1("10.  Turning the AI on later"));
children.push(NUM("Copy .env.example to a file called .env", "n5"));
children.push(NUM("Open it and put the key in.", "n5"));
children.push(NUM("In the app, turn on \"Use the model for wording\".", "n5"));
children.push(P("Nothing else changes. The checks are the same, the numbers " +
  "are the same, the sheet is the same. The model chooses words and decides " +
  "keep or drop on the candidates, and that is all it is allowed to do."));
children.push(P("The tests run with no key at all, and they always will."));

// ---------------------------------------------------------------- 11
children.push(H1("11.  What comes next, in order"));
children.push(NUM("The eight checks docs/score.py still lists as missing.", "n6"));
children.push(NUM("R. cra/codegen.py is a stub today. The plan is Tplyr and " +
  "r2rtf for the output, haven for the data, diffdf for the comparison and " +
  "renv so the versions are pinned. This is piece two of the project and it " +
  "is a big one.", "n6"));
children.push(NUM("Read the SAP itself, so spec.txt is no longer written by " +
  "hand.", "n6"));
children.push(NUM("CDISC controlled terminology and MedDRA.", "n6"));
children.push(NUM("Learned checks: a rule taken from your own finished " +
  "studies, tested against the whole programme before it is turned on, so " +
  "you can see it fires on this study and on nothing else.", "n6"));

// ---------------------------------------------------------------- 12
children.push(H1("12.  If something goes wrong"));
children.push(table([
  ["What you see", "What to do"],
  ["'python' is not recognised", "PATH was not ticked during install. Reinstall Python and tick it."],
  ["No module named streamlit", "Run pip install -r requirements.txt again and read the last line."],
  ["No outputs found", "Run python make_sample_outputs.py"],
  ["The Review page is empty", "Check the study in the sidebar is DEMO-BE-101. The others are clean on purpose."],
  ["A test fails after your change", "Read the test name. It says which real finding you just broke."],
  ["The sheet has findings you disagree with", "Reject them on the Review page. They will not come back, because the key is stable."],
], [3100, 5700]));

children.push(new Paragraph({ spacing: { before: 400 },
  children: [new TextRun({ text: "Start with section 4. Four commands.",
                           bold: true, size: 23, color: NAVY, font: "Calibri" })] }));

const doc = new Document({
  numbering,
  styles: { default: { document: { run: { font: "Calibri", size: 21 } } } },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },   // US Letter
        margin: { top: convertInchesToTwip(0.9), bottom: convertInchesToTwip(0.9),
                  left: convertInchesToTwip(1), right: convertInchesToTwip(1) },
      },
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("START_HERE.docx", buf);
  console.log("wrote START_HERE.docx");
});
