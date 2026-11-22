<div align="center">

# Bitwarden Duplicate Merger

**Encuentra y fusiona los inicios de sesión duplicados de tu caja fuerte de Bitwarden, con una pantalla de revisión antes de cualquier cambio.**

[![tests](https://github.com/ThomLaurent/bitwarden-duplicate-merger/actions/workflows/tests.yml/badge.svg)](https://github.com/ThomLaurent/bitwarden-duplicate-merger/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/ThomLaurent/bitwarden-duplicate-merger?label=download)](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
[![license](https://img.shields.io/badge/license-Unlicense-blue)](LICENSE)

[English](README.md) · [Français](README.fr.md) · Español · [Deutsch](README.de.md) · [简体中文](README.zh-CN.md)

<img src="docs/screenshots/review-conflict.png" alt="Pantalla de revisión: tres inicios de sesión de Steam con dos contraseñas distintas" width="900">

</div>

Tras importar contraseñas desde un navegador u otro gestor, una caja fuerte suele contener la misma cuenta varias veces: `www.amazon.es`, `login.amazon.es` y `amazon.es/ap/signin`, con el mismo usuario y la misma contraseña. Bitwarden no permite fusionarlos, y hacerlo a mano con cientos de entradas lleva horas.

Esta herramienta agrupa esos duplicados, propone una fusión para cada grupo, te deja revisar y cambiar cada decisión en una página web local y luego aplica solo lo que has validado, mediante la CLI oficial de Bitwarden.

## Cómo funciona

1. **Inicia la herramienta.** La CLI de Bitwarden desbloquea la caja fuerte y se abre una página en tu navegador.
2. **Revisa las sugerencias.** Los inicios de sesión con el mismo dominio y usuario se agrupan. Los grupos que la regla no puede resolver sola (contraseñas distintas, passkeys...) se marcan para ti.
3. **Cambia lo que quieras**: elemento conservado, nombre, contraseña, TOTP, notas, URIs, elementos que dejar fuera. Agrupa entradas a mano si hace falta (`ebay.es` y `ebay.com`).
4. **Para y continúa cuando quieras.** Las decisiones se guardan en un archivo, incluso tras reiniciar.
5. **Aplica** todos los grupos validados o solo algunos. Un informe muestra lo realizado, empezando por lo que decidiste distinto de la regla.

## Garantías

- **Tu contraseña maestra nunca llega a la herramienta.** Solo la lee la CLI de Bitwarden; la herramienta recibe la clave de sesión y la guarda en memoria.
- **Ningún secreto se escribe en disco ni en registros.** Contraseñas, claves TOTP, campos y notas se comparan en memoria. La página muestra uno solo si pulsas "show".
- **Nada cambia sin tu validación**, y solo se aplican los grupos validados.
- **Ningún plan obsoleto.** Justo antes de cada grupo, la herramienta comprueba con Bitwarden que ningún elemento cambió desde tu revisión. Si cambió, el grupo se omite y se indica.
- **Reversible.** Los duplicados van a la papelera de Bitwarden (30 días), los elementos conservados mantienen su ID, adjuntos y passkeys, y se hace una copia cifrada antes de aplicar.
- **Solo local.** La página se sirve en `127.0.0.1` con un token aleatorio. Sin acceso a la red salvo `bw` hacia tu servidor de Bitwarden.
- **Pequeña y legible.** Unas 2.000 líneas de Python y JavaScript, solo biblioteca estándar, sin dependencias que auditar.

## Inicio rápido

1. Instala la [CLI de Bitwarden](https://bitwarden.com/help/cli/) (`bw`).
2. Descarga el ejecutable para tu sistema desde la [última versión](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest) y ejecútalo desde una terminal:
   ```bash
   ./bw-dedupe-linux-x64
   ```
   O desde el código fuente con cualquier Python 3.10+, sin instalar nada:
   ```bash
   git clone https://github.com/ThomLaurent/bitwarden-duplicate-merger
   cd bitwarden-duplicate-merger
   python bw_dedupe.py
   ```
3. Desbloquea la caja fuerte cuando `bw` lo pida y revisa en la página que se abre.

Los ejecutables incluyen su propio Python: siguen funcionando con cualquier versión de Python que tengas, mientras `bw` mantenga sus comandos. Cada uno se compila con GitHub Actions desde este repositorio y se verifica con:

```bash
gh attestation verify bw-dedupe-linux-x64 --repo ThomLaurent/bitwarden-duplicate-merger
```

Más detalles (en inglés): [guía de uso](docs/USAGE.md).

## Estado del proyecto

Esta herramienta se comparte **tal cual** y probablemente no se mejorará. La hice para limpiar mi propia caja fuerte y preferí compartirla abiertamente en lugar de guardarla para mí. Espero que te ahorre el tiempo y los tokens de crear lo mismo y, sobre todo, las horas de fusionar cientos de entradas a mano.

Puede que las issues y pull requests no reciban respuesta. Los forks son bienvenidos: el código es de dominio público ([Unlicense](LICENSE)), y [AGENTS.md](AGENTS.md) lo explica a ti y a los asistentes de programación con IA.

Sin relación con Bitwarden, Inc. "Bitwarden" es una marca de Bitwarden, Inc.
