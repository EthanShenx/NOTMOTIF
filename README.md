# NOTMOTIF

Turn any word into a sequence-logo (motif) style image.

![NOTMOTIF](docs/notmotif.png)

## Install

```bash
pip install git+https://github.com/EthanShenx/NOTMOTIF
```

## Use

```bash
notmotif serve                                         # local website at http://localhost:8765
notmotif Happy -o happy.png --width 1200 --height 400  # command line (see notmotif --help)
```

```python
import notmotif
notmotif.save("Happy", "happy.png", width=1200, height=400, noise=0.3)
```

MIT License.
