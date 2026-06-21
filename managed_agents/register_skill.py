#!/usr/bin/env python3
"""Registra (o versiona) la skill custom 'snapshot-cambiario' en el workspace.

Las skills custom de Managed Agents se suben por la Skills API y quedan
disponibles a nivel workspace. Este script las sube desde la carpeta local
`skills/snapshot-cambiario/` y te devuelve el `skill_id` que después tenés que
poner en `.env` como SKILL_ID para que el orquestador la adjunte al agente.

Es un paso de SETUP: corrés esto una vez (y de nuevo solo si editás el
SKILL.md, para crear una versión nueva).

Uso:
  python register_skill.py            # crea la skill (o una versión si ya existe SKILL_ID)
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

import anthropic
from anthropic.lib import files_from_dir

# Carpeta local de la skill (debe contener SKILL.md).
SKILL_DIR = os.path.join(os.path.dirname(__file__), "skills", "snapshot-cambiario")
DISPLAY_TITLE = "Snapshot cambiario"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(
            f"Falta la variable de entorno {name}. "
            f"Copiá .env.example a .env y completá ANTHROPIC_API_KEY."
        )
    return value


def main() -> None:
    require_env("ANTHROPIC_API_KEY")  # el SDK la relee del entorno

    if not os.path.isfile(os.path.join(SKILL_DIR, "SKILL.md")):
        sys.exit(f"No se encontró SKILL.md en {SKILL_DIR}.")

    client = anthropic.Anthropic()
    if not hasattr(client.beta, "skills"):
        sys.exit(
            "Tu versión de 'anthropic' no expone client.beta.skills (Skills API). "
            "Actualizá: pip install -U anthropic"
        )

    existing = os.environ.get("SKILL_ID")
    if existing:
        # Ya hay una skill registrada: subimos una versión nueva.
        version = client.beta.skills.versions.create(
            skill_id=existing,
            files=files_from_dir(SKILL_DIR),
        )
        print(f"[versión] nueva versión de {existing}: {version.version}")
        return

    skill = client.beta.skills.create(
        display_title=DISPLAY_TITLE,
        files=files_from_dir(SKILL_DIR),
    )
    print(f"[creada] skill_id = {skill.id}")
    print(f"[creada] última versión = {skill.latest_version}")
    print()
    print("Pegá esta línea en tu .env y corré el orquestador con --reset:")
    print(f"  SKILL_ID={skill.id}")


if __name__ == "__main__":
    main()
