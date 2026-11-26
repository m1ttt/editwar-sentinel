# Cómo contribuir

## Ramas (GitFlow)

| Rama | Nace de | Se fusiona en | Tipo de merge |
|---|---|---|---|
| `feature/<issue>-<slug>` | `develop` | `develop` | Squash |
| `release/<versión>` | `develop` | `main` y `develop` | Merge commit |
| `hotfix/<versión>` | `main` | `main` y `develop` | Merge commit |

Ejemplo: `feature/12-detector-reverts`, `release/1.0.0`, `hotfix/1.0.1`.

- Cada rama `feature` corresponde a una sola issue. Su PR la cierra con `Closes #N`.
- Las `feature` se fusionan con squash: cada issue queda como un solo commit en `develop`.
- `release` y `hotfix` se fusionan con merge commit para conservar el historial.
- Después de fusionar una `release` en `main`, crea el tag `vX.Y.Z`. El pipeline publica las imágenes `X.Y.Z` y `X.Y`.

## Commits

Usa Conventional Commits:

```
feat: agrega detector de reverts por idioma
fix: corrige el desalojo de la ventana deslizante
test: cubre el cooldown del detector
ci: publica el reporte de pruebas
docs: documenta el despliegue en k3d
```

## Ramas protegidas

`main` y `develop` están protegidas:

- Solo cambian por pull request.
- El pipeline debe estar en verde (calidad y pruebas unitarias).
- El PR necesita una aprobación. GitHub no deja que el autor apruebe su propio PR, así que otro colaborador revisa.

## Antes de abrir un PR

```bash
make lint
make test
```
