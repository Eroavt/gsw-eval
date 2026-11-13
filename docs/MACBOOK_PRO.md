# Run the local models on a Mac

For any team member with an Apple Silicon Mac (M1 or newer). Gemma 3 27B needs 48 GB of RAM.
About 15 minutes of your time; then the Mac works alone. No API key is needed.

## 1. Get the code

Open Terminal:

```bash
mkdir -p ~/dev && cd ~/dev
git clone https://github.com/Eroavt/gsw-eval.git
cd gsw-eval
git config user.name "Your Name"
git config user.email "you@example.com"
```

Keep the repo out of iCloud folders (Desktop, Documents): iCloud breaks Git repositories.
If Git asks you to log in: use your GitHub name and a token from
github.com → Settings → Developer settings → Personal access tokens. With the GitHub CLI
(`brew install gh`, then `gh auth login`) the script also opens the pull request for you.

## 2. Add SwissDial (9 MB)

Download `swissdial.zip` from the team Drive folder gsw-eval-data → "swissdial (team only)"
and unzip it inside `data/`:

```bash
cd ~/dev/gsw-eval/data && unzip ~/Downloads/swissdial.zip && cd ..
ls data/swissdial/data1.1/   # sentences_ch_de_transcribed.json and _numerics.json
```

## 3. Start one job

```bash
scripts/run_local_models.sh dose     # stress test: 3 models, stronger noise (about 2 hours)
scripts/run_local_models.sh fresh    # 3 models on the fresh set (minutes)
```

The first run downloads the models (about 50 GB). Without a job name the script runs every
job; most are already cached, so name the job you were asked to run.

- Plug in the charger. The script keeps the Mac awake.
- You can stop it with Ctrl-C and start it again. Nothing is lost: every output is cached.
- At the end the script commits the results on a new branch `runs/<job>-<computer>-<date>`,
  pushes it and opens a pull request (or prints the link to open one). `main` is protected,
  so results only reach it through that pull request with green tests.
- Two people can run jobs at the same time: the model caches merge without conflicts.
