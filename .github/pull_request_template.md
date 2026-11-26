## Qué cambia

<!-- Describe el cambio en una o dos frases. -->

## Issue

Closes #

## Cómo se probó

<!-- Comandos que ejecutaste y resultado. Ejemplo: make test, make lint, make deploy en k3d. -->

## Checklist

- [ ] La rama sigue GitFlow (`feature/<issue>-<slug>`, `release/<versión>` o `hotfix/<versión>`).
- [ ] El título del PR sigue Conventional Commits (`feat:`, `fix:`, `test:`, `ci:`, `docs:`).
- [ ] `make lint` y `make test` pasan en local.
- [ ] La cobertura de cada paquete es de 80 % o más.
- [ ] Si cambian los manifiestos, `kubectl kustomize deploy/k8s/overlays/<local|dev|prod>` renderiza sin error.
- [ ] Actualicé la documentación si el cambio la afecta.
