# homelab
*full deployment of homelab via ansible and docker compose*


## TODO
### Navidrome
- setup navidrome container
- container mount in /opt/data/music for songs

### Backup
backup playbook:
version: 2

backends:
  backblaze:
    type: b2
    path: 'my-bucket:homelab-backup'
    key: '{{ lookup("env", "B2_KEY") }}'
    env:
      B2_ACCOUNT_ID: 'YOUR_ID'
      B2_ACCOUNT_KEY: 'YOUR_KEY'

  local-ssd:
    type: local
    path: /mnt/secondary_ssd/backups

locations:
  # ---------------------------------------------------------
  # LOCATION 1: CLOUD (Once a night, Deep Storage)
  # ---------------------------------------------------------
  homelab-cloud:
    from: /opt/homelab
    to: backblaze
    cron: '0 3 * * *' # Runs at 3:00 AM
    hooks:
      before:
        # Stop everything to ensure clean files
        - docker stop seafile-mysql immich_postgres navidrome radicale
      after:
        # Start everything back up
        - docker start seafile-mysql immich_postgres navidrome radicale
    forget:
      keep-daily: 7
      keep-weekly: 4

  # ---------------------------------------------------------
  # LOCATION 2: LOCAL SSD (Twice a day, Fast Recovery)
  # ---------------------------------------------------------
  homelab-local:
    from: /opt/homelab
    to: local-ssd
    cron: '0 6,18 * * *' # Changed to 6:00 AM & 6:00 PM (Avoids usage hours?)
    hooks:
      before:
        # Stops services for ~2 mins to copy files to SSD
        - docker stop seafile-mysql immich_postgres navidrome radicale
      after:
        - docker start seafile-mysql immich_postgres navidrome radicale
    forget:
      keep-daily: 14
      keep-weekly: 2

restore script (to run while services are not up):
autorestic restore -l homelab-local --from local-ssd --to /opt/homelab
autorestic restore -l homelab-cloud --from backblaze --to /opt/homelab

## installation steps

## ansible


## docker compose
