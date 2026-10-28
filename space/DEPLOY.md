# Deploying the Space

Steps for the owner after subscribing to Hugging Face PRO. Replace `<HF_USERNAME>` with the
Hugging Face user name. The Space repository's root is the contents of this `space/` folder:
`app.py`, `requirements.txt` and `README.md` (its YAML header is the Space configuration).
`DEPLOY.md` stays here.

Why PRO: Gradio Spaces on the free CPU Basic hardware (2 vCPU, 16 GB RAM, $0 an hour) can only be
created with PRO; without it the Hub answers HTTP 402. CPU Basic pauses a Space after 48 hours
without visitors; the next visitor waits for a cold start.

## 0. Optional: test locally

```sh
conda create -n sa-space python=3.12 -y && conda activate sa-space
pip install -r space/requirements.txt
python space/app.py   # http://127.0.0.1:7860
```

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
  --commit-message "Section Anything Free mode demo"
```

This puts `app.py`, `requirements.txt` and `README.md` at the root of the Space repository and
replaces the README the Hub created. There are no binary files: the example paper is downloaded
from arXiv on first use, so no Xet/LFS set-up is needed.

Or with git (password: a write token):

```sh
git clone https://huggingface.co/spaces/<HF_USERNAME>/section-anything ../sa-hf-space
cp space/app.py space/requirements.txt space/README.md ../sa-hf-space/
cd ../sa-hf-space
git add app.py requirements.txt README.md
git commit -m "Section Anything Free mode demo"
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

1. "Try the example paper": 25 pages, 19 sections, the heading tree from "Visual Instruction
   Tuning" down to "F Prompts", the Abstract's text, and a JSON file.
2. Upload any PDF with a text layer: the summary line shows pages, sections and seconds.
3. A scanned PDF (no text layer) shows the OCR message.

If the example button reports that arXiv could not be reached, uploads still work; the container
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

- New library release: bump `section-anything==` in `requirements.txt`, then upload again.
- New Gradio: change `sdk_version` in `README.md` and the `gradio==` pin together, to a release
  at least two weeks old, and test locally first (`python app.py`).
- Settings live in the Space page's Settings tab (hardware, pause, visibility). CPU Basic has no
  hourly charge; only the PRO subscription is billed.
