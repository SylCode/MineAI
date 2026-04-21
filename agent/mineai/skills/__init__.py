"""
skills/__init__.py

High-level action macros that chain multiple primitive bot actions.
The planner can call these instead of individual actions when a skill
maps directly to a current goal.

Usage in planner (future):
    from mineai.skills import wood_gathering
    await wood_gathering.run(client, state)
"""
