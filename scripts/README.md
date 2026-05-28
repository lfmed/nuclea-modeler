# Operational scripts

Utilitários administrativos do Núclea Modeler. Não fazem parte do runtime do app
— são CLIs autônomos para operações ocasionais.

## `backup.py`

Snapshot completo das 25 tabelas Delta do app para um Volume UC, formato Parquet.

```bash
# Backup completo com label timestamp UTC (default)
python -m scripts.backup --volume /Volumes/main/default/nuclea_backups

# Apenas algumas tabelas
python -m scripts.backup \
  --volume /Volumes/main/default/nuclea_backups \
  --tables entities attributes relationships

# Dry-run: lista o que seria feito
python -m scripts.backup --volume /Volumes/... --dry-run

# Label customizado (ex: antes de migration arriscada)
python -m scripts.backup --volume /Volumes/... --label pre-migration-010
```

**Quando usar:**
- Antes de aplicar migration que muda schema (DROP COLUMN, ALTER TYPE).
- Snapshot trimestral para audit / compliance.
- Cross-region copy: usar um Volume em region diferente.

**Quando NÃO usar:**
- Restore granular linha-a-linha → use Delta Time Travel (`@v123` ou `TIMESTAMP AS OF`).
- Backup automático recorrente → configure um Databricks Job que chama este script.

**Auth:** lê `DATABRICKS_HOST` + `DATABRICKS_TOKEN` ou usa default auth do SDK.

## Como agendar como Job

```python
# job_backup.py — colocar em um repo Job ou notebook
import subprocess

subprocess.run(
    ["python", "-m", "scripts.backup",
     "--volume", "/Volumes/main/default/nuclea_backups"],
    check=True,
)
```

Agendar com cron `0 3 * * 1` (toda segunda 3am) e retenção via lifecycle policy
do Volume.
