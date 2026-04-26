"""Test package for the league app.

Currently no tests live here directly; league behavior is exercised via
app.tests (e.g. test_league*). This package exists so that test runners
that ask for `league.tests` can resolve the module without a loader
ImportError.
"""
