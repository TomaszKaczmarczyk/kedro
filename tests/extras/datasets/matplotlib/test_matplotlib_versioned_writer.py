# Copyright 2020 QuantumBlack Visual Analytics Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
# NONINFRINGEMENT. IN NO EVENT WILL THE LICENSOR OR OTHER CONTRIBUTORS
# BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF, OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# The QuantumBlack Visual Analytics Limited ("QuantumBlack") name and logo
# (either separately or in combination, "QuantumBlack Trademarks") are
# trademarks of QuantumBlack. The License does not grant you any right or
# license to the QuantumBlack Trademarks. You may not use the QuantumBlack
# Trademarks or any confusingly similar mark as a trademark for your product,
#     or use the QuantumBlack Trademarks in any other manner that might cause
# confusion in the marketplace, including but not limited to in advertising,
# on websites, or on software.
#
# See the License for the specific language governing permissions and
# limitations under the License.


import json

import matplotlib
import matplotlib.pyplot as plt
import pytest
import s3fs
from moto import mock_s3
from s3fs import S3FileSystem

from kedro.extras.datasets.matplotlib import MatplotlibVersionedWriter
from kedro.io import DataSetError
from kedro.io.core import Version

BUCKET_NAME = "test_bucket"
AWS_CREDENTIALS = dict(aws_access_key_id="testing", aws_secret_access_key="testing")
CREDENTIALS = {"client_kwargs": AWS_CREDENTIALS}
KEY_PATH = "matplotlib"
COLOUR_LIST = ["blue", "green", "red"]
FULL_PATH = "s3://{}/{}".format(BUCKET_NAME, KEY_PATH)

matplotlib.use("Agg")  # Disable interactive mode


@pytest.fixture
def mock_single_plot():
    plt.plot([1, 2, 3], [4, 5, 6])
    return plt


@pytest.fixture
def mock_list_plot():
    plots_list = []
    colour = "red"
    for index in range(5):  # pylint: disable=unused-variable
        plots_list.append(plt.figure())
        plt.plot([1, 2, 3], [4, 5, 6], color=colour)
    return plots_list


@pytest.fixture
def mock_dict_plot():
    plots_dict = {}
    for colour in COLOUR_LIST:
        plots_dict[colour] = plt.figure()
        plt.plot([1, 2, 3], [4, 5, 6], color=colour)
        plt.close()
    return plots_dict


@pytest.fixture
def mocked_s3_bucket():
    """Create a bucket for testing using moto."""
    with mock_s3():
        conn = s3fs.core.boto3.client("s3", **AWS_CREDENTIALS)
        conn.create_bucket(Bucket=BUCKET_NAME)
        yield conn


@pytest.fixture
def mocked_encrypted_s3_bucket():
    bucket_policy = {
        "Version": "2012-10-17",
        "Id": "PutObjPolicy",
        "Statement": [
            {
                "Sid": "DenyUnEncryptedObjectUploads",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:PutObject",
                "Resource": "arn:aws:s3:::{}/*".format(BUCKET_NAME),
                "Condition": {"Null": {"s3:x-amz-server-side-encryption": "aws:kms"}},
            }
        ],
    }
    bucket_policy = json.dumps(bucket_policy)

    with mock_s3():
        conn = s3fs.core.boto3.client("s3", **AWS_CREDENTIALS)
        conn.create_bucket(Bucket=BUCKET_NAME)
        conn.put_bucket_policy(Bucket=BUCKET_NAME, Policy=bucket_policy)
        yield conn


@pytest.fixture()
def s3fs_cleanup():
    # clear cache for clean mocked s3 bucket each time
    yield
    S3FileSystem.cachable = False


@pytest.fixture
def plot_writer(
    mocked_s3_bucket, fs_args, save_args
):  # pylint: disable=unused-argument
    return MatplotlibVersionedWriter(
        filepath=FULL_PATH,
        fs_args=fs_args,
        credentials=CREDENTIALS,
        save_args=save_args,
    )


@pytest.fixture
def versioned_plot_writer(
    mocked_s3_bucket, load_version, save_version
):  # pylint: disable=unused-argument
    return MatplotlibVersionedWriter(
        filepath=FULL_PATH,
        credentials=CREDENTIALS,
        version=Version(load_version, save_version),
    )


def test_save_data(tmp_path, mock_single_plot, plot_writer, mocked_s3_bucket):
    """Test saving single matplotlib plot to S3."""

    plot_writer.save(mock_single_plot)

    download_path = tmp_path / "downloaded_image.png"
    actual_filepath = tmp_path / "locally_saved.png"

    plt.savefig(str(actual_filepath))

    mocked_s3_bucket.download_file(BUCKET_NAME, KEY_PATH, str(download_path))

    assert actual_filepath.read_bytes() == download_path.read_bytes()
    assert plot_writer._fs_open_args_save == {"mode": "wb"}


def test_list_save(tmp_path, mock_list_plot, plot_writer, mocked_s3_bucket):
    """Test saving list of plots to S3."""

    plot_writer.save(mock_list_plot)

    for index in range(5):

        download_path = tmp_path / "downloaded_image.png"
        actual_filepath = tmp_path / "locally_saved.png"

        mock_list_plot[index].savefig(str(actual_filepath))

        _key_path = "{}/{}.png".format(KEY_PATH, index)

        mocked_s3_bucket.download_file(BUCKET_NAME, _key_path, str(download_path))

        assert actual_filepath.read_bytes() == download_path.read_bytes()


def test_dict_save(tmp_path, mock_dict_plot, plot_writer, mocked_s3_bucket):
    """Test saving dictionary of plots to S3."""

    plot_writer.save(mock_dict_plot)

    for colour in COLOUR_LIST:

        download_path = tmp_path / "downloaded_image.png"
        actual_filepath = tmp_path / "locally_saved.png"

        mock_dict_plot[colour].savefig(str(actual_filepath))

        _key_path = "{}/{}".format(KEY_PATH, colour)

        mocked_s3_bucket.download_file(BUCKET_NAME, _key_path, str(download_path))

        assert actual_filepath.read_bytes() == download_path.read_bytes()


def test_bad_credentials(mock_dict_plot):
    """Test writing with bad credentials"""
    bad_writer = MatplotlibVersionedWriter(
        filepath=FULL_PATH,
        credentials={
            "client_kwargs": {
                "aws_access_key_id": "not_for_testing",
                "aws_secret_access_key": "definitely_not_for_testing",
            }
        },
    )

    pattern = r"The AWS Access Key Id you provided does not exist in our records"
    with pytest.raises(DataSetError, match=pattern):
        bad_writer.save(mock_dict_plot)


def test_fs_args(tmp_path, mock_single_plot, mocked_encrypted_s3_bucket):
    """Test writing to encrypted bucket"""
    normal_encryped_writer = MatplotlibVersionedWriter(
        fs_args={"s3_additional_kwargs": {"ServerSideEncryption": "AES256"}},
        filepath=FULL_PATH,
        credentials=CREDENTIALS,
    )

    normal_encryped_writer.save(mock_single_plot)

    download_path = tmp_path / "downloaded_image.png"
    actual_filepath = tmp_path / "locally_saved.png"

    mock_single_plot.savefig(str(actual_filepath))

    mocked_encrypted_s3_bucket.download_file(BUCKET_NAME, KEY_PATH, str(download_path))

    assert actual_filepath.read_bytes() == download_path.read_bytes()


@pytest.mark.parametrize(
    "fs_args", [{"open_args_save": {"mode": "w", "compression": "gzip"}}], indirect=True
)
def test_open_extra_args(plot_writer, fs_args):
    assert plot_writer._fs_open_args_save == fs_args["open_args_save"]


@pytest.mark.parametrize("save_args", [{"k1": "v1", "index": "value"}], indirect=True)
def test_save_extra_params(plot_writer, save_args):
    """Test overriding the default save arguments."""
    assert plot_writer._save_args == save_args


def test_load_fail(plot_writer):
    pattern = r"Loading not supported for `MatplotlibVersionedWriter`"
    with pytest.raises(DataSetError, match=pattern):
        plot_writer.load()


@pytest.mark.usefixtures("s3fs_cleanup")
def test_exists_single(mock_single_plot, plot_writer):
    assert not plot_writer.exists()
    plot_writer.save(mock_single_plot)
    assert plot_writer.exists()


@pytest.mark.usefixtures("s3fs_cleanup")
def test_exists_multiple(mock_dict_plot, plot_writer):
    assert not plot_writer.exists()
    plot_writer.save(mock_dict_plot)
    assert plot_writer.exists()


def test_release(mocker):
    fs_mock = mocker.patch("fsspec.filesystem").return_value
    data_set = MatplotlibVersionedWriter(filepath=FULL_PATH)
    data_set.release()
    fs_mock.invalidate_cache.assert_called_once_with(
        "{}/{}".format(BUCKET_NAME, KEY_PATH)
    )


class TestMatplotlibWriterVersioned:
    def test_version_str_repr(self, load_version, save_version):
        """Test that version is in string representation of the class instance
        when applicable."""
        filepath = "chart.png"
        chart = MatplotlibVersionedWriter(filepath=filepath)
        chart_versioned = MatplotlibVersionedWriter(
            filepath=filepath, version=Version(load_version, save_version)
        )
        assert filepath in str(chart)
        assert "version" not in str(chart)

        assert filepath in str(chart_versioned)
        ver_str = "version=Version(load={}, save='{}')".format(
            load_version, save_version
        )
        assert ver_str in str(chart_versioned)

    def test_prevent_overwrite(self, versioned_plot_writer, mock_single_plot):
        """Check the error when attempting to override the data set if the
        corresponding CSV file for a given save version already exists."""
        versioned_plot_writer.save(mock_single_plot)
        pattern = (
            r"Save path \`.+\` for MatplotlibVersionedWriter\(.+\) must "
            r"not exist if versioning is enabled\."
        )
        with pytest.raises(DataSetError, match=pattern):
            versioned_plot_writer.save(mock_single_plot)
