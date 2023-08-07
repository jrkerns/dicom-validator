import logging

import pytest
from pydicom import Sequence
from pydicom.dataset import Dataset

from dicom_validator.tests.utils import has_tag_error
from dicom_validator.validator.iod_validator import IODValidator

pytestmark = pytest.mark.usefixtures("disable_logging")


def new_data_set(shared_macros, per_frame_macros):
    """Create a DICOM data set with the given attributes"""
    data_set = Dataset()
    # Enhanced X-Ray Angiographic Image
    data_set.SOPClassUID = "1.2.840.10008.5.1.4.1.1.12.1.1"
    data_set.PatientName = "XXX"
    data_set.PatientID = "ZZZ"
    data_set.ImageType = "DERIVED"
    data_set.InstanceNumber = "1"
    data_set.ContentDate = "20000101"
    data_set.ContentTime = "120000"
    data_set.NumberOfFrames = "3"
    shared_groups = Sequence()
    if shared_macros:
        item = Dataset()
        for macro in shared_macros:
            add_contents_to_item(item, macro)
        shared_groups.append(item)
    data_set.SharedFunctionalGroupsSequence = shared_groups

    per_frame_groups = Sequence()
    if per_frame_macros:
        for i in range(3):
            # we don't care about the tag contents, we just put the same values
            # into each per-frame item
            item = Dataset()
            for macro in per_frame_macros:
                add_contents_to_item(item, macro)
            per_frame_groups.append(item)
    data_set.PerFrameFunctionalGroupsSequence = per_frame_groups

    data_set.file_meta = Dataset()
    data_set.is_implicit_VR = False
    data_set.is_little_endian = True
    return data_set


def add_contents_to_item(item, contents):
    for name, content in contents.items():
        if isinstance(content, list):
            value = Sequence()
            add_items_to_sequence(value, content)
        else:
            value = content
        setattr(item, name, value)


def add_items_to_sequence(sequence, contents):
    for content in contents:
        item = Dataset()
        add_contents_to_item(item, content)
        sequence.append(item)


@pytest.fixture
def validator(iod_info, module_info, request):
    marker = request.node.get_closest_marker("shared_macros")
    shared_macros = {} if marker is None else marker.args[0]
    marker = request.node.get_closest_marker("per_frame_macros")
    per_frame_macros = {} if marker is None else marker.args[0]
    data_set = new_data_set(shared_macros, per_frame_macros)
    return IODValidator(data_set, iod_info, module_info, None, logging.ERROR)


FRAME_ANATOMY = {
    "FrameAnatomySequence": [
        {
            "FrameLaterality": "R",
            "AnatomicRegionSequence": [
                {
                    "CodeValue": "T-D3000",
                    "CodingSchemeDesignator": "SRT",
                    "CodeMeaning": "Chest",
                }
            ],
        }
    ]
}

FRAME_VOI_LUT = {
    "FrameVOILUTSequence": [{"WindowCenter": "7200", "WindowWidth": "12800"}]
}


class TestIODValidatorFuncGroups:
    """Tests IODValidator for functional groups."""

    def ensure_group_result(self, result):
        assert "Multi-frame Functional Groups" in result
        return result["Multi-frame Functional Groups"]

    def test_missing_func_groups(self, iod_info, module_info):
        data_set = new_data_set({}, {})
        del data_set[0x52009229]
        del data_set[0x52009230]
        validator = IODValidator(data_set, iod_info, module_info, None, logging.ERROR)
        result = validator.validate()
        group_result = self.ensure_group_result(result)
        assert "Tag (5200,9229) is missing" in group_result
        assert "Tag (5200,9230) is missing" in group_result

    def test_empty_func_groups(self, validator):
        result = validator.validate()
        group_result = self.ensure_group_result(result).keys()
        assert "Tag (5200,9229) is empty" in group_result
        assert "Tag (5200,9230) is empty" in group_result

    @pytest.mark.shared_macros([FRAME_ANATOMY])
    @pytest.mark.per_frame_macros([FRAME_VOI_LUT])
    def test_missing_sequences(self, validator):
        result = validator.validate()
        # Frame Content Sequence (mandatory, missing)
        assert has_tag_error(result, "Frame Content", "(0020,9111)", "missing")
        # Frame Anatomy Sequence (present in shared groups)
        assert not has_tag_error(result, "Frame Anatomy", "(0020,9071)", "missing")
        # Frame VOI LUT Sequence (present in per-frame groups)
        assert not has_tag_error(result, "Frame VOI LUT", "(0028,9132)", "missing")
        # Referenced Image Sequence (not mandatory)
        assert not has_tag_error(result, "Referenced Image", "(0008,1140)", "missing")

    @pytest.mark.skip("Not yet implemented")
    @pytest.mark.shared_macros([FRAME_ANATOMY])
    @pytest.mark.per_frame_macros([FRAME_ANATOMY])
    def test_sequence_in_shared_and_per_frame(self, validator):
        result = validator.validate()
        # Frame Anatomy Sequence (present in shared groups)
        assert has_tag_error(result, "Frame Anatomy", "(0020,9071)", "not allowed")
