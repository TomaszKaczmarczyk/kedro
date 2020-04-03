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


"""``MatplotlibVersionedWriter`` saves matplotlib objects as image file(s) to an underlying
filesystem (e.g. local, S3, GCS). Versioning is supported"""

import copy
import io
from pathlib import PurePath, PurePosixPath
from typing import Any, Dict, List, Union

import fsspec
from matplotlib.pyplot import figure

from kedro.io.core import (
    AbstractVersionedDataSet,
    DataSetError,
    Version,
    get_filepath_str,
    get_protocol_and_path,
)


class MatplotlibVersionedWriter(AbstractVersionedDataSet):
    """``MatplotlibVersionedWriter`` saves matplotlib objects as image file(s) to an underlying
    filesystem (e.g. local, S3, GCS). Versioning is supported

    Note: loading charts is currently not supported.

    Example:
    ::

        >>> import matplotlib.pyplot as plt
        >>> from kedro.extras.datasets.matplotlib import MatplotlibVersionedWriter
        >>>
        >>> # Saving single plot
        >>> plt.plot([1, 2, 3], [4, 5, 6])
        >>> single_plot_writer = MatplotlibVersionedWriter(
        >>>     filepath="matplot_lib_single_plot.png"
        >>> )
        >>> single_plot_writer.save(plt)
        >>> plt.close()
        >>>
        >>> # Saving dictionary of plots
        >>> plots_dict = dict()
        >>> for colour in ["blue", "green", "red"]:
        >>>     plots_dict[colour] = plt.figure()
        >>>     plt.plot([1, 2, 3], [4, 5, 6], color=colour)
        >>>     plt.close()
        >>> dict_plot_writer = MatplotlibVersionedWriter(
        >>>     filepath="matplotlib_dict"
        >>> )
        >>> dict_plot_writer.save(plots_dict)
        >>>
        >>> # Saving list of plots
        >>> plots_list = []
        >>> for index in range(5):
        >>>     plots_list.append(plt.figure())
        >>>     plt.plot([1,2,3],[4,5,6])
        >>>     plt.close()
        >>> list_plot_writer = MatplotlibVersionedWriter(
        >>>     filepath="matplotlib_list"
        >>> )
        >>> list_plot_writer.save(plots_list)

    """

    DEFAULT_LOAD_ARGS = {}  # type: Dict[str, Any]
    DEFAULT_SAVE_ARGS = {}  # type: Dict[str, Any]

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        filepath: str,
        fs_args: Dict[str, Any] = None,
        credentials: Dict[str, Any] = None,
        save_args: Dict[str, Any] = None,
        layer: str = None,
        version: Version = None,
    ) -> None:
        """
        Creates a new instance of ``MatplotlibVersionedWriter`` pointing to a concrete file
        on a specific filesystem.

        Args:
        filepath: Key path to a matplot object file(s) prefixed with a protocol like `s3://`.
            If prefix is not provided, `file` protocol (local filesystem) will be used.
            The prefix should be any protocol supported by ``fsspec``.
        fs_args: Extra arguments to pass into underlying filesystem class constructor
            (e.g. `{"project": "my-project"}` for ``GCSFileSystem``), as well as
            to pass to the filesystem's `open` method through nested key `open_args_save`.
            Here you can find all available arguments for `open`:
            https://filesystem-spec.readthedocs.io/en/latest/api.html#fsspec.spec.AbstractFileSystem.open
            All defaults are preserved, except `mode`, which is set to `wb` when saving.
        credentials: Credentials required to get access to the underlying filesystem.
            E.g. for ``S3FileSystem`` it should look like:
            `{'client_kwargs': {'aws_access_key_id': '<id>', 'aws_secret_access_key': '<key>'}}`
        save_args: Save args passed to `plt.savefig`. See
            https://matplotlib.org/api/_as_gen/matplotlib.pyplot.savefig.html
        layer: The data layer according to the data engineering convention:
            https://kedro.readthedocs.io/en/stable/06_resources/01_faq.html#what-is-data-engineering-convention
        version: If specified, should be an instance of
            ``kedro.io.core.Version``. If its ``save`` attribute is None,
            save version will be autogenerated.
        """

        _credentials = copy.deepcopy(credentials) or {}
        _fs_args = copy.deepcopy(fs_args) or {}
        _fs_open_args_save = _fs_args.pop("open_args_save", {})
        _fs_open_args_save.setdefault("mode", "wb")

        self._fs_args = _fs_args
        self._fs_open_args_save = _fs_open_args_save
        self._layer = layer

        protocol, path = get_protocol_and_path(filepath, version)

        self._protocol = protocol
        self._fs = fsspec.filesystem(self._protocol, **_credentials, **_fs_args)

        super().__init__(
            filepath=PurePosixPath(path),
            version=version,
            exists_function=self._fs.exists,
            glob_function=self._fs.glob,
        )

        # Handle default load and save arguments
        self._save_args = copy.deepcopy(self.DEFAULT_SAVE_ARGS)
        if save_args is not None:
            self._save_args.update(save_args)

    def _describe(self) -> Dict[str, Any]:
        return dict(
            filepath=self._filepath,
            protocol=self._protocol,
            fs_args=self._fs_args,
            save_args=self._save_args,
            version=self._version,
            layer=self._layer,
        )

    def _load(self) -> None:
        raise DataSetError(
            "Loading not supported for `{}`".format(self.__class__.__name__)
        )

    def _save(self, data: Union[figure, List[figure], Dict[str, figure]]) -> None:
        if isinstance(data, list):
            for index, plot in enumerate(data):
                full_key_path = self._fs.pathsep.join(
                    [
                        get_filepath_str(self._get_save_path(), self._protocol),
                        "{}.png".format(index),
                    ]
                )
                self._save_to_fs(full_key_path=full_key_path, plot=plot)

        elif isinstance(data, dict):
            for plot_name, plot in data.items():
                full_key_path = self._fs.pathsep.join(
                    [get_filepath_str(self._get_save_path(), self._protocol), plot_name]
                )
                self._save_to_fs(full_key_path=full_key_path, plot=plot)

        else:
            full_key_path = get_filepath_str(self._get_save_path(), self._protocol)
            self._save_to_fs(full_key_path=full_key_path, plot=data)

        self._invalidate_cache()

    def _get_save_path(self) -> PurePath:
        if not self._version:
            # When versioning is disabled, return original filepath
            return self._filepath

        save_version = self.resolve_save_version()
        versioned_path = self._get_versioned_path(save_version)  # type: ignore

        # Don't check if path exists for multiFile charts to enable versioning
        if self._exists_function(str(versioned_path)) and not self._save_args.get(
            "multiFile"
        ):
            raise DataSetError(
                "Save path `{}` for {} must not exist if versioning "
                "is enabled.".format(versioned_path, str(self))
            )

        return versioned_path

    def _save_to_fs(self, full_key_path: str, plot: figure):
        bytes_buffer = io.BytesIO()
        plot.savefig(bytes_buffer, **self._save_args)

        with self._fs.open(full_key_path, **self._fs_open_args_save) as fs_file:
            fs_file.write(bytes_buffer.getvalue())

    def _exists(self) -> bool:
        load_path = get_filepath_str(self._filepath, self._protocol)
        return self._fs.exists(load_path)

    def _release(self) -> None:
        super()._release()
        self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        """Invalidate underlying filesystem caches."""
        filepath = get_filepath_str(self._filepath, self._protocol)
        self._fs.invalidate_cache(filepath)