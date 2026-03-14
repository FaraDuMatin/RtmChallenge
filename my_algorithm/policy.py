from aerohacks.policy.base import Policy
from aerohacks.core.models import Observation, Plan, ActionStep, ActionType, Position2D
import math

from .helpers import distance, is_point_safe

# Max horizontal speed per tick (from scenario vehicle_limits)
MAX_SPEED = 15.0
# Traffic avoidance distance
TRAFFIC_DANGER = 120.0
# How far to offset laterally when dodging a constraint
DETOUR_OFFSET = 2000.0


class MyPolicy(Policy):
    """
    Simple direct-to-goal policy with:
    - Altitude strategy: fly at layer 4 when far (avoids most constraints at 1,2,3)
    - Constraint checking with lateral detours
    - Basic traffic avoidance
    """

    def step(self, obs: Observation) -> Plan:
        pos = obs.ownship_state.position
        alt = obs.ownship_state.alt_layer
        goal_pos = obs.mission_goal.region.center()
        goal_alt = obs.mission_goal.target_alt_layer if obs.mission_goal.target_alt_layer is not None else alt
        constraints = obs.active_constraints or []
        dist_to_goal = distance(pos, goal_pos)

        # --- Altitude strategy ---
        # Fly high (layer 4) when far to bypass low-altitude constraints.
        # Descend to goal altitude when close enough.
        if dist_to_goal > 5000.0:
            plan_alt = 4
        elif dist_to_goal > 2000.0:
            plan_alt = goal_alt + 1 if goal_alt < 4 else goal_alt
        else:
            plan_alt = goal_alt

        # If planned alt is also blocked at our position, try other layers
        if not is_point_safe(pos.x, pos.y, constraints, plan_alt):
            for try_alt in [4, 3, 2, 1]:
                if is_point_safe(pos.x, pos.y, constraints, try_alt):
                    plan_alt = try_alt
                    break

        # --- Build 5 waypoints ---
        steps = []
        cur = pos
        for _ in range(5):
            # Traffic check: dodge if NPC too close
            dodge = self._traffic_dodge(obs, cur, plan_alt)
            if dodge:
                steps.append(ActionStep(
                    action_type=ActionType.WAYPOINT,
                    target_position=dodge,
                    target_alt_layer=plan_alt,
                ))
                cur = dodge
                continue

            # Compute direct waypoint toward goal
            wp = self._step_toward(cur, goal_pos, MAX_SPEED)

            # Check if waypoint is safe at planned altitude
            if is_point_safe(wp.x, wp.y, constraints, plan_alt):
                steps.append(ActionStep(
                    action_type=ActionType.WAYPOINT,
                    target_position=wp,
                    target_alt_layer=plan_alt,
                ))
                cur = wp
            else:
                # Try lateral detours (left and right perpendicular to goal direction)
                detour = self._find_detour(cur, goal_pos, constraints, plan_alt)
                if detour:
                    steps.append(ActionStep(
                        action_type=ActionType.WAYPOINT,
                        target_position=detour,
                        target_alt_layer=plan_alt,
                    ))
                    cur = detour
                else:
                    # If all blocked, hold position
                    steps.append(ActionStep(action_type=ActionType.HOLD))

        return Plan(steps=steps)

    @staticmethod
    def _step_toward(cur: Position2D, target: Position2D, speed: float) -> Position2D:
        """Move one step toward target, clamped to speed."""
        dx = target.x - cur.x
        dy = target.y - cur.y
        d = math.hypot(dx, dy)
        if d <= speed:
            return Position2D(x=target.x, y=target.y)
        return Position2D(x=cur.x + dx / d * speed, y=cur.y + dy / d * speed)

    @staticmethod
    def _find_detour(cur: Position2D, goal: Position2D, constraints, alt: int):
        """Try lateral detours perpendicular to the goal direction."""
        dx = goal.x - cur.x
        dy = goal.y - cur.y
        d = math.hypot(dx, dy)
        if d < 1.0:
            return None
        ux, uy = dx / d, dy / d
        # Perpendicular directions
        px, py = -uy, ux

        # Try multiple offsets and both sides
        for offset in [DETOUR_OFFSET, DETOUR_OFFSET * 1.5, DETOUR_OFFSET * 2.0]:
            for sign in [1.0, -1.0]:
                wx = cur.x + ux * MAX_SPEED * 0.5 + px * sign * offset * (MAX_SPEED / offset)
                wy = cur.y + uy * MAX_SPEED * 0.5 + py * sign * offset * (MAX_SPEED / offset)
                wp = Position2D(x=wx, y=wy)
                if is_point_safe(wx, wy, constraints, alt):
                    return wp
        return None

    @staticmethod
    def _traffic_dodge(obs: Observation, pos: Position2D, alt: int):
        """If an NPC is dangerously close, return a dodge waypoint. Otherwise None."""
        for t in (obs.traffic_tracks or []):
            if abs(t.alt_layer - alt) > 1:
                continue
            dx = t.position.x - pos.x
            dy = t.position.y - pos.y
            d = math.hypot(dx, dy)
            if d < TRAFFIC_DANGER and d > 0.1:
                # Move perpendicular to the NPC direction (away from NPC)
                away_x = -dx / d * MAX_SPEED
                away_y = -dy / d * MAX_SPEED
                return Position2D(x=pos.x + away_x, y=pos.y + away_y)
        return None
