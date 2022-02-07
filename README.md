# robot-cellpainter

dependencies: python 3.10

optional dev dependencies: pyright, entr

## installation

```
pip install --editable .
```

## test

```
cellpainter --cell-paint 6,6
```

configs:

```
--live
--live-no-incu
--simulator
--forward
--dry-wall
--dry-run
```

## network

machine        | ip
---            | ---
Ubuntu NUC     | 10.0.0.55
Windows NUC    | 10.0.0.56
UR control box | 10.0.0.112

The windows nuc runs the labrobots http endpoint on `10.10.0.56:5050`.

