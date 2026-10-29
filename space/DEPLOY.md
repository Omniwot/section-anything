# Deploying the Space

Steps for the owner after subscribing to Hugging Face PRO. Replace `<HF_USERNAME>` with the
Hugging Face user name. The Space repository's root is the contents of this `space/` folder:
`app.py`, `requirements.txt`, `README.md` (its YAML header is the Space configuration),
`examples/` (the saved runs, JSON) and `make_examples.py` (how they were made; not run on the
Space). `DEPLOY.md` stays here.

The Space needs the `section-anything` version pinned in `requirements.txt` to be on PyPI: upload
only after that release is published.

Why PRO: Gradio Spaces on the free CPU Basic hardware (2 vCPU, 16 GB RAM, $0 an hour) can only be
created with PRO; without it the Hub answers HTTP 402. CPU Basic pauses a Space after 48 hours
without visitors; the next visitor waits for a cold start.

## 0. Optional: test locally

```sh
conda create -n sa-space python=3.12 -y && conda activate sa-space
pip install -r space/requirements.txt
python space/app.py   # http://127.0.0.1:7860
```

Before the pinned `section-anything` release is on PyPI, install the other requirements and run
the checkout's package instead: `PYTHONPATH=packages/section-anything/src python space/app.py`.

## 1. Create the Space

Web: https://huggingface.co/new-space

- Owner: `<HF_USERNAME>`; Space name: `section-anything`
- License: `apache-2.0`
- SDK: Gradio, template Blank
- Hardware: CPU Basic (free)
- Visibility: Public

Or with the `hf` CLI (`pip install -U huggingface_hub`; the token needs write access):

```sh
hf auth login
hf repos create <HF_USERNAME>/section-anything --type space --sdk gradio --flavor cpu-basic --public
```

## 2. Upload the files

From the root of a checkout of this repository, on the branch that holds `space/`:

```sh
hf upload <HF_USERNAME>/section-anything space . --type space \
  --exclude DEPLOY.md --exclude "*__pycache__*" \
  --commit-message "Section Anything demo: Free live, saved Quick check and Standard on three examples"
```

This puts `app.py`, `requirements.txt`, `README.md`, `make_examples.py` and `examples/` at the
root of the Space repository and replaces the README the Hub created. There are no binary files:
the example papers are downloaded from arXiv on first use, so no Xet/LFS set-up is needed.

Or with git (password: a write token):

```sh
git clone https://huggingface.co/spaces/<HF_USERNAME>/section-anything ../sa-hf-space
cp -R space/app.py space/requirements.txt space/README.md space/make_examples.py space/examples ../sa-hf-space/
cd ../sa-hf-space
git add app.py requirements.txt README.md make_examples.py examples
git commit -m "Section Anything demo: Free live, saved Quick check and Standard on three examples"
git push
```

## 3. Check the build

Each upload starts a build. Watch it on the Space page (Logs: Build, then Container) or:

```sh
hf spaces wait <HF_USERNAME>/section-anything --timeout 15m   # exit code 0 once RUNNING
hf spaces logs <HF_USERNAME>/section-anything --build         # if the build fails
hf spaces logs <HF_USERNAME>/section-anything                 # app output
```

Expected:

- The build installs Python 3.12 (`python_version` in the README), Gradio 6.30.0 (`sdk_version`)
  and `requirements.txt`. If the build reports a Gradio conflict, `sdk_version` and the `gradio`
  pin in `requirements.txt` differ: make them equal.
- The container log shows a line starting `* Running on local URL:` (port 7860).

Then open `https://huggingface.co/spaces/<HF_USERNAME>/section-anything` and check:

1. Click each of the three example buttons with Mode on Free: "Visual Instruction Tuning" gives
   25 pages and 19 sections, "Knowledge Is Flat" 13 and 28, "Thermalization, Chaos and
   Hydrodynamics" 88 and 85, each with "(Free mode, run live on this Space ...)", the paper's
   note, a table of the three saved runs and a JSON file.
2. Switch Mode to Quick check and to Standard on each example. The status line starts with
   "Saved run, section-anything 0.1.5, gpt-6-luna, 2026-10-28, cost $..." and the section counts
   are 19 and 20, 30 and 22, 83 and 65. The section text box shows text. If the status line says
   "Text shown for N of M sections", this Space's extraction differs from the saved run's in
   those sections (for example after a change to the pinned pdfplumber, pdfminer.six or
   pypdfium2): their text is withheld rather than shown wrong.
3. Upload any PDF with a text layer: the summary line shows pages, sections and seconds. Switch to
   Quick check: one line says these modes run here only as saved runs on the examples, and Free
   stays on screen.
4. A scanned PDF (no text layer) shows the OCR message.

If an example button reports that arXiv could not be reached, uploads still work; the container
log shows `example download failed: <error type>`. Click again later: each click retries until one
download succeeds, and the file is then kept until the Space restarts.

## 4. Link it from the main README

Once it runs, add a badge next to the Colab badge in the repository's `README.md`:

```markdown
[![Open in Spaces](https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-sm.svg)](https://huggingface.co/spaces/<HF_USERNAME>/section-anything)
```

and a sentence after the demo paragraph, in the README's tone, for example:
"Try Free mode in the browser on the [Hugging Face Space](https://huggingface.co/spaces/<HF_USERNAME>/section-anything)
(no key; don't upload confidential documents)." The website (`site/`) and the Colab notebook can
link to the same URL.

## Updating

- New library release: bump `section-anything==` in `requirements.txt`, then upload again. The
  saved runs keep their own version label (0.1.5) until they are made again.
- To make the saved runs again (for a new release, or other papers in `EXAMPLES`): from `space/`,
  `python make_examples.py --estimate` (no model call), then
  `OPENAI_API_KEY=... python make_examples.py` (sends the three papers' text to the model; about
  $0.02 with gpt-6-luna on 28 Oct 2026). READoc heading-tree TEDS is added afterwards with
  READoc's own scorer, which is not part of this repository. Then test locally and upload.
- New Gradio: change `sdk_version` in `README.md` and the `gradio==` pin together, to a release
  at least two weeks old, and test locally first (`python app.py`).
- Settings live in the Space page's Settings tab (hardware, pause, visibility). CPU Basic has no
  hourly charge; only the PRO subscription is billed.
