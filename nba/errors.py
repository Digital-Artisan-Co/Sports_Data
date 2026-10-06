"""Stable exception identity across provider hot reloads and open Streamlit sessions."""


class ProviderError(RuntimeError):
    """A provider could not supply the requested real data."""
