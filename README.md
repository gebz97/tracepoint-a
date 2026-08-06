# tpa - tracepoint-a infrastructure inventory CLI

Collects infrastructure inventory (host info, disks, NICs, mounts, users/groups,
daemons, packages) from hosts over SSH and stores it in a PostgreSQL database.

## Requirements

- Python 3.10+
- PostgreSQL (with `psycopg` driver support)
- SSH access to target hosts (key-based or password auth)

## Setup

```sh
pip install -r requirements.txt   # click, sqlalchemy, alembic, paramiko, pyyaml, psycopg
cp example.config.yaml config.yaml
```

### Configuration

`config.yaml` (or the file pointed to by `TPA_CONFIG`):

```yaml
database:
  url: "postgresql+psycopg://tpa_user:changeme@localhost:5432/tpa"

ssh:
  port: 22
  timeout: 30
  max_workers: 32

credentials:
  default:
    type: pkey            # or "userpass"
    username: svc_account
    key_path: /home/chad/.ssh/id_rsa
    passphrase: null      # or "userpass": password: ...
```

- `ssh.max_workers` controls the concurrency of parallel host collection.
- `credentials.default` is the single credential used for all hosts; add more
  entries under `credentials` as needed (currently only `default` is used).

### Database migrations

```sh
python tpa.py migrate
# or directly: alembic upgrade head
```

## Usage

```
python tpa.py <command>
```

### Load hosts (`synchosts`)

Reads a CSV of hosts, SSHes into each, collects host info, and upserts into the DB:

```sh
python tpa.py synchosts hosts.csv
```

CSV layout - `host` is required; adjacent property columns are mapped onto
dedicated host attributes, and any other column is stored in the `extra` JSONB:

```csv
host,environment,service,function,role,sequence,owner,description,patching_group,has_dr,dr_method,custom_field
web01.example.com,prod,checkout,web,app,01,team-a,"Frontend node",week1,yes,backup-site,anything
db01.example.com,prod,database,db,primary,02,team-b,,week2,no,,
```

Host property columns:

| Column          | Type    | Notes                                      |
| --------------- | ------- | ------------------------------------------ |
| `environment`   | varchar | e.g. `prod`, `dev`, `test`                 |
| `service`       | varchar |                                            |
| `function`      | varchar |                                            |
| `role`          | varchar |                                            |
| `sequence`      | varchar |                                            |
| `owner`         | varchar |                                            |
| `description`   | text    |                                            |
| `patching_group`| varchar |                                            |
| `has_dr`        | boolean | accepts `true/1/yes/y/on`, empty = unset   |
| `dr_method`     | varchar |                                            |

Any other column in the CSV (e.g. `custom_field`) is stored in `hosts.extra`.

### Sync resource inventory

Runs over every host currently in the database:

```sh
python tpa.py syncdisks     # disks
python tpa.py syncnet       # NICs / IP addresses
python tpa.py syncmounts    # mounts
python tpa.py syncusers     # users and groups (with sudo flags)
python tpa.py syncdaemons   # systemd daemons
python tpa.py syncpkg       # installed packages
python tpa.py syncall       # all of the above
```

Resources no longer present on a host are marked `is_stale` rather than deleted.

### Reports (`get`)

Export any inventory table as CSV to stdout and/or a file:

```sh
python tpa.py get hosts --stdout
python tpa.py get hosts --csv hosts-report.csv
python tpa.py get disks --csv disks.csv
python tpa.py get net --csv net.csv
python tpa.py get mounts --stdout
python tpa.py get groups --csv groups.csv
python tpa.py get users --csv users.csv
python tpa.py get daemons --csv daemons.csv
python tpa.py get pkg --csv packages.csv
```

Available reports: `hosts`, `disks`, `net`, `mounts`, `groups`, `users`,
`daemons`, `pkg`. At least one of `--csv` or `--stdout` is required.

## Typical workflow

1. `cp example.config.yaml config.yaml` and fill in database URL + SSH credentials.
2. `python tpa.py migrate`
3. `python tpa.py synchosts hosts.csv`
4. `python tpa.py syncall`
5. `python tpa.py get hosts --stdout`

## Project layout

- `tpa.py` - CLI entry point
- `lib/commands/` - click commands (synchosts, sync*, get, migrate)
- `lib/collectors/` - per-resource SSH collectors
- `lib/models.py` - SQLAlchemy models
- `lib/sync_runner.py` - shared parallel sync logic
- `lib/ssh.py` - SSH connection handling
- `alembic/` - schema migrations
