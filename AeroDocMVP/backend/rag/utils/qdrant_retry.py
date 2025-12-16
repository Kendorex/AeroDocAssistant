import time
from typing import Callable, TypeVar
from qdrant_client.http.exceptions import UnexpectedResponse

T = TypeVar("T")
from utils.qdrant_store import QdrantStore

StoreType = QdrantStore



def wait_qdrant_ready(store: StoreType, timeout_s: int) -> None:
    """Ожидание готовности Qdrant."""
    t0 = time.time()
    attempts = 0
    
    while time.time() - t0 < timeout_s:
        attempts += 1
        try:
            collections = store.client.get_collections()
            print(f"[wait] Qdrant готов! Получено коллекций: {len(collections.collections)}")
            return
        except UnexpectedResponse as e:
            if hasattr(e, 'status_code'):
                print(f"[wait] Попытка {attempts}: HTTP {e.status_code}")
            else:
                print(f"[wait] Попытка {attempts}: {repr(e)}")
            time.sleep(1)
        except Exception as e:
            print(f"[wait] Попытка {attempts}: {repr(e)}")
            time.sleep(1)
    
    raise RuntimeError(f"Qdrant не готов после {timeout_s} секунд ({attempts} попыток)")


def retry(fn: Callable[[], T], *, what: str, retry_count: int, sleep_s: float) -> T:
    """Повторная попытка выполнения функции при ошибках."""
    for attempt in range(1, retry_count + 1):
        try:
            return fn()
        except UnexpectedResponse as e:
            content = getattr(e, "content", None)
            print(f"[retry {attempt}/{retry_count}] {what}: HTTP {getattr(e, 'status_code', '?')}")
            if content:
                try:
                    print(content.decode("utf-8", errors="replace")[:4000])
                except Exception:
                    print(str(content)[:4000])
            time.sleep(sleep_s)
        except Exception as e:
            print(f"[retry {attempt}/{retry_count}] {what}: {repr(e)}")
            time.sleep(sleep_s)
    raise RuntimeError(f"Failed: {what}")