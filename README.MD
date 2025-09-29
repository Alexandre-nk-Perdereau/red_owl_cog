# Red Owl Cog

## Variables requises

* `FAL_KEY` : clé API FAL (obligatoire pour les fonctions qui l’utilisent)

## Option 1 — **systemd** (recommandé)

1. Créez un fichier `.env` à côté du cog, par ex. :

```
/home/<user>/cogs/red_owl_cog/.env
```

Contenu minimal :

```
FAL_KEY=xxxxxxxxxxxxxxxx
```

2. Pointez le service systemd dessus via `EnvironmentFile=` :

```ini
# /etc/systemd/system/redbot.service
[Unit]
Description=Red Discord Bot (redowl)
After=network-online.target

[Service]
Type=simple
User=<user>
WorkingDirectory=/home/<user>/cogs/red_owl_cog
EnvironmentFile=/home/<user>/cogs/red_owl_cog/.env
ExecStart=/home/<user>/redenv/bin/redbot redowl
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

3. Rechargez et démarrez :

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now redbot
```

4. Logs :

```bash
journalctl -u redbot -f -o cat
```

## Option 2 — Script bash (alternative simple)

Si vous ne souhaitez pas utiliser systemd :

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
cd /home/<user>/cogs/red_owl_cog
source "$HOME/redenv/bin/activate"
if [ -f .env ]; then
  set -a; source .env; set +a
fi
exec redbot redowl >> "$HOME/logs/redbot.log" 2>&1 &
```