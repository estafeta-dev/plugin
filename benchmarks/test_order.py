#!/usr/bin/env python3
"""Offline checks of the seeded case order and arm prompts; needs no Codex CLI."""
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit  # noqa: E402
import run  # noqa: E402


class OrderTest(unittest.TestCase):
    def test_every_case_once_in_balanced_blocks(self):
        for seed in [0, 1, 7, 20261012, 20261013, 2**40]:
            for scenarios, arms, reps in [(run.SCENARIOS, run.ARMS, 3), (['game', 'app'], ['baseline', 'workflow'], 5)]:
                order = run.balanced_order(scenarios, arms, reps, seed)
                self.assertEqual(order, run.balanced_order(scenarios, arms, reps, seed))
                self.assertEqual(sorted(map(tuple, order)), sorted(itertools.product(scenarios, arms, range(1, reps+1))))
                self.assertEqual([r for _, _, r in order], sorted(r for _, _, r in order))
                for start in range(0, len(order), len(arms)):
                    block = order[start:start+len(arms)]
                    self.assertEqual(len({(s, r) for s, _, r in block}), 1)
                    self.assertEqual(sorted(a for _, a, _ in block), sorted(arms))
        self.assertGreater(len({str(run.balanced_order(run.SCENARIOS, run.ARMS, 3, seed)) for seed in range(10)}), 1)

    def test_each_arm_takes_each_position_equally_often_per_scenario(self):
        for seed in [0, 1, 7, 20261012, 20261013]:
            for reps in (3, 6):
                order = run.balanced_order(run.SCENARIOS, run.ARMS, reps, seed)
                for scenario in run.SCENARIOS:
                    rows = [arm for s, arm, _ in order if s == scenario]
                    blocks = [rows[i:i+len(run.ARMS)] for i in range(0, len(rows), len(run.ARMS))]
                    for position in range(len(run.ARMS)):
                        counts = {arm: sum(block[position] == arm for block in blocks) for arm in run.ARMS}
                        self.assertEqual(set(counts.values()), {reps // len(run.ARMS)}, (seed, scenario, position, counts))

    def test_arm_block_replaces_activation_slot(self):
        lite = run.LITE.read_text()
        tail = '\nDevelopment brief (stage 2):\nBRIEF\n'
        prompts = {arm: run.compose_prompt('COMMON\n', arm, 2, 'BRIEF', lite) for arm in run.ARMS}
        self.assertEqual(prompts['baseline'], 'COMMON\n'+tail)
        self.assertEqual(prompts['workflow'], 'COMMON\n'+run.ACTIVATION+tail)
        self.assertTrue(prompts['lite'].startswith('COMMON\n\n'+lite) and prompts['lite'].endswith(tail))
        self.assertIn('$session-handover', run.ACTIVATION)
        for arm, prompt in prompts.items():
            for claimed in run.ARMS:
                self.assertEqual(audit.prompt_ok(claimed, prompt, lite), claimed == arm, (arm, claimed))


if __name__ == '__main__':
    unittest.main()
