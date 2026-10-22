# Run the local models on the MacBook Pro

About 30 minutes of your time. Then the Mac works alone for about 2 hours.

## 1. Get the code

Open Terminal:

```bash
mkdir -p ~/dev && cd ~/dev
git clone https://github.com/Eroavt/gsw-eval.git
cd gsw-eval
git switch feat/core-pipeline
```

If Git asks you to log in: use your GitHub name and a token from
github.com → Settings → Developer settings → Personal access tokens.

## 2. Copy SwissDial (9 MB)

From the MacBook Air, AirDrop the folder `~/dev/gsw-eval/data/swissdial`.
Put it on the MacBook Pro at `~/dev/gsw-eval/data/swissdial`.

## 3. Start

```bash
scripts/run_local_models.sh
```

- Plug in the charger. The script keeps the Mac awake.
- You can stop it with Ctrl-C and start it again. Nothing is lost.
- At the end it pushes the results to GitHub. If that fails, AirDrop the folder
  `results/cache/` back to the Air.
