"""Static-only fixture. This file is read by the candidate scanner."""
import yaml


def unsafe_parse(config_text):
    return yaml.load(config_text, Loader=yaml.Loader)


def safe_parse(config_text):
    return yaml.safe_load(config_text)
