# robot-cellpainter

dependencies: python 3.10

optional dev dependencies: pyright, entr

## installation

```
pip install --editable .
```

## test

```
cellpainter --cell-paint 6,6 --dry-run
```

Github actions is set up, check .github/workflows/test.yml. One way to run this locally is to use [`act`](https://github.com/nektos/act).

## network

machine        | ip
---            | ---
Ubuntu NUC     | 10.0.0.55
Windows NUC    | 10.0.0.56
UR control box | 10.0.0.112

The windows nuc runs the labrobots http endpoint on `10.10.0.56:5050`.
