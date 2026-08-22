import unittest
from neural.neural_orchestrator import get_neural_orchestrator
from neural.experience_encoder import get_encoder
from neural.prediction_engine import get_prediction_engine
from neural.reward_engine import get_reward_engine

class TestNeuralLearningFabric(unittest.TestCase):
    def test_orchestrator_initialization(self):
        orchestrator = get_neural_orchestrator()
        self.assertTrue(orchestrator.active)

    def test_experience_encoder(self):
        encoder = get_encoder()
        latent = encoder.encode({"event": "test"})
        self.assertEqual(len(latent), 256)

    def test_prediction_engine(self):
        engine = get_prediction_engine()
        engine.register_prediction("event_1", {"expected": True})
        error = engine.evaluate_outcome("event_1", {"actual": False})
        self.assertGreater(error, 0.0)

    def test_reward_engine(self):
        engine = get_reward_engine()
        reward = engine.compute_reward(0.8, 0.5)
        self.assertGreater(reward, 0.0)

if __name__ == '__main__':
    unittest.main()
