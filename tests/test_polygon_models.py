import unittest

from src.polygon.models import (
    Package,
    PackageState,
    PackageType,
    ProblemFiles,
    ResourceAsset,
    ResourceStage,
    TestGroup as PolygonTestGroup,
)


class PolygonModelsTest(unittest.TestCase):
    def test_problem_files_from_dict_parses_nested_properties(self):
        files = ProblemFiles.from_dict(
            {
                "resourceFiles": [
                    {
                        "name": "testlib.h",
                        "modificationTimeSeconds": 1700000000,
                        "length": 123,
                        "resourceAdvancedProperties": {
                            "forTypes": "cpp.g++17",
                            "main": False,
                            "stages": ["COMPILE"],
                            "assets": ["VALIDATOR"],
                        },
                    }
                ],
                "sourceFiles": [
                    {
                        "name": "validator.cpp",
                        "modificationTimeSeconds": 1700000001,
                        "length": 456,
                        "sourceType": "cpp.gcc14-64-msys2-g++23",
                    }
                ],
                "auxFiles": [],
            }
        )

        self.assertEqual(files.resourceFiles[0].resourceAdvancedProperties.forTypes, "cpp.g++17")
        self.assertEqual(files.resourceFiles[0].resourceAdvancedProperties.stages, [ResourceStage.COMPILE])
        self.assertEqual(files.resourceFiles[0].resourceAdvancedProperties.assets, [ResourceAsset.VALIDATOR])
        self.assertEqual(files.sourceFiles[0].sourceType, "cpp.gcc14-64-msys2-g++23")

    def test_package_from_dict_parses_state_and_type(self):
        package = Package.from_dict(
            {
                "id": "12",
                "revision": "34",
                "creationTimeSeconds": 1700000002,
                "state": "READY",
                "comment": "main build",
                "type": "linux",
            }
        )

        self.assertEqual(package.id, 12)
        self.assertEqual(package.revision, 34)
        self.assertEqual(package.state, PackageState.READY)
        self.assertEqual(package.type, PackageType.LINUX)

    def test_test_group_from_dict_parses_policies(self):
        group = PolygonTestGroup.from_dict(
            {
                "name": "samples",
                "pointsPolicy": "EACH_TEST",
                "feedbackPolicy": "POINTS",
                "dependencies": ["pretests"],
            }
        )

        self.assertEqual(group.name, "samples")
        self.assertEqual(group.pointsPolicy.value, "EACH_TEST")
        self.assertEqual(group.feedbackPolicy.value, "POINTS")
        self.assertEqual(group.dependencies, ["pretests"])


if __name__ == "__main__":
    unittest.main()
