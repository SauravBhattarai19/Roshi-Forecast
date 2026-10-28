"""IMERG over the Roshi basin for the Sept 2024 rehearsal (with a 30-day warm-up)."""
from MRRpy import Config
from MRRpy.gee.imerg_gee import download_imerg

cfg = Config.from_file("../model.yaml")
cfg.OUTPUT_DIR = "../static"
cfg.update_output_paths()
cfg.PRECIP_IMERG_DIR = "imerg_2024"
cfg.EVENT_START_UTC = "2024-08-25 00:00"
cfg.TOTAL_SIMULATION_TIME_HOURS = 37 * 24
print(download_imerg(cfg))
