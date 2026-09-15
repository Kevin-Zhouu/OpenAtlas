import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("OPENATLAS_DATA", ROOT / ".data")).resolve()
SKILLS = Path(os.getenv("OPENATLAS_SKILLS", ROOT / "skills")).resolve()
FRONTEND = ROOT / "frontend" / "dist"
GENERATION_IMAGE = os.getenv("OPENATLAS_GENERATION_IMAGE", "openatlas-generation:local")
TIMEOUT = int(os.getenv("OPENATLAS_JOB_TIMEOUT", "7200"))
# Model loaders fetch embedded textures through object URLs before decoding them.
# Allow those local blobs while artifact_csp still confines network fetches.
ARTIFACT_CSP = "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval' http: https: blob:; style-src 'unsafe-inline' http: https:; img-src http: https: data: blob:; font-src http: https: data:; connect-src http: https: blob:; media-src http: https: data: blob:; worker-src blob:; frame-src 'none'; form-action 'none'; base-uri 'none'"


# Serving middleware narrows http(s) sources to the immutable artifact directory.
def artifact_csp(base):
    return ARTIFACT_CSP.replace("http: https:", base)

# Generation tools share these limits; inference runs remotely.
GENERATION_MEMORY = os.getenv("OPENATLAS_GENERATION_MEMORY", "4g")
GENERATION_CPUS = float(os.getenv("OPENATLAS_GENERATION_CPUS", "4"))
