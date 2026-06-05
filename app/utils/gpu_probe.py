import logging
import subprocess

logger = logging.getLogger(__name__)


def get_system_metrics() -> dict:
    """Lee métricas del sistema desde /proc y /sys (sin dependencias extra)."""
    metrics = {
        "cpu_pct": 0.0,
        "ram_used_gb": 0.0,
        "ram_total_gb": 0.0,
        "ram_pct": 0.0,
        "temp_c": 0.0,
        "gpu_pct": 0,
        "disk_used_gb": 0.0,
        "disk_total_gb": 0.0,
        "disk_pct": 0.0,
    }

    # CPU load (1-min average)
    try:
        with open("/proc/loadavg") as f:
            load1 = float(f.read().split()[0])
        with open("/proc/cpuinfo") as f:
            ncpus = f.read().count("processor\t:")
        metrics["cpu_pct"] = round(min(load1 / max(ncpus, 1) * 100, 100), 1)
    except Exception:
        pass

    # RAM
    try:
        with open("/proc/meminfo") as f:
            lines = {l.split(":")[0]: int(l.split()[1]) for l in f if ":" in l}
        total_kb = lines.get("MemTotal", 0)
        avail_kb = lines.get("MemAvailable", 0)
        used_kb = total_kb - avail_kb
        metrics["ram_total_gb"] = round(total_kb / 1024 / 1024, 1)
        metrics["ram_used_gb"] = round(used_kb / 1024 / 1024, 1)
        metrics["ram_pct"] = round(used_kb / total_kb * 100, 1) if total_kb else 0
    except Exception:
        pass

    # Temperatura (Tegra thermal zones)
    try:
        import glob
        temps = []
        for path in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
            try:
                with open(path) as f:
                    temps.append(int(f.read().strip()) / 1000)
            except Exception:
                pass
        if temps:
            metrics["temp_c"] = round(max(temps), 1)
    except Exception:
        pass

    # GPU load (Tegra sysfs)
    try:
        with open("/sys/devices/gpu.0/load") as f:
            metrics["gpu_pct"] = int(f.read().strip())
    except Exception:
        pass

    # Disco
    try:
        import shutil
        usage = shutil.disk_usage("/app")
        metrics["disk_total_gb"] = round(usage.total / 1e9, 1)
        metrics["disk_used_gb"] = round(usage.used / 1e9, 1)
        metrics["disk_pct"] = round(usage.used / usage.total * 100, 1)
    except Exception:
        pass

    return metrics


def get_compute_backend() -> str:
    """Detecta si CUDA está disponible y soporta SM_11.0. Retorna 'cuda' o 'cpu'."""
    try:
        import torch
        if torch.cuda.is_available():
            major, minor = torch.cuda.get_device_capability()
            if major >= 11 and float(torch.version.cuda or 0) >= 13.0:
                logger.info("GPU Blackwell SM_%d.%d detectada — usando CUDA", major, minor)
                return "cuda"
            logger.warning("GPU detectada pero CUDA no compatible con SM_%d.%d", major, minor)
    except ImportError:
        pass
    return "cpu"
