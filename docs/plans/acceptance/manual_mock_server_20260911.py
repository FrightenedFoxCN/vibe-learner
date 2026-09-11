from pathlib import Path
from tempfile import TemporaryDirectory
import uvicorn
from app.app_factory import create_app
from app.core.settings import Settings
with TemporaryDirectory(prefix='vibe-manual-independent-') as directory:
    root = Path(directory)
    settings = Settings(database_url=f"sqlite:///{root / 'domain.db'}", storage_root=str(root / 'data'), plan_provider='mock', ocr_engine='disabled', allowed_origins=('http://127.0.0.1:3430',))
    uvicorn.run(create_app(settings=settings), host='127.0.0.1', port=19001)
