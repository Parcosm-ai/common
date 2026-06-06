import os
import tempfile
import unittest

from lib.casted_dict import CastedDict


class TestCastedDict(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.conf_path = os.path.join(self.temp_dir.name, "tests.conf")
        self.conf_local_path = self.conf_path + ".local"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_conf(self, path, rows):
        with open(path, "w") as f:
            for row in rows:
                f.write("\t".join(row) + "\n")

    def test_nested_list(self):
        self.write_conf(self.conf_path, [["nested", "[1, [2, 3], 4]"]])
        d = CastedDict(self.conf_path)
        self.assertEqual([1, [2, 3], 4], d["nested"])

    def test_multiline_list(self):
        self.write_conf(self.conf_path, [["nested", "[1, [2,\n   3], 4]"]])
        d = CastedDict(self.conf_path)
        self.assertEqual([1, [2, 3], 4], d["nested"])

    def test_load_from_conf_only(self):
        self.write_conf(
            self.conf_path,
            [["foo", "123", "int"], ["bar", "True", "bool"]],
        )
        d = CastedDict(self.conf_path)
        self.assertEqual(d["foo"], 123)
        self.assertEqual(d["bar"], True)

    def test_load_from_conf_local_only(self):
        self.write_conf(
            self.conf_local_path,
            [["foo", "456", "int"], ["baz", "hello", "str"]],
        )
        d = CastedDict(self.conf_path)
        self.assertEqual(d["foo"], 456)
        self.assertEqual(d["baz"], "hello")
        self.assertIsNone(d.get("bar"))

    def test_load_from_both_conf_and_conf_local(self):
        self.write_conf(
            self.conf_path,
            [["foo", "123", "int"], ["bar", "True", "bool"]],
        )
        self.write_conf(
            self.conf_local_path,
            [["foo", "789", "int"], ["baz", "world", "str"]],
        )
        d = CastedDict(self.conf_path)
        self.assertEqual(d["foo"], 789)
        self.assertEqual(d["bar"], True)
        self.assertEqual(d["baz"], "world")

    def test_not_found(self):
        bad_path = os.path.join(self.temp_dir.name, "tests-fail.conf")
        with self.assertRaises(FileNotFoundError):
            CastedDict(bad_path)


if __name__ == "__main__":
    unittest.main()
