#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Adapter 
"""

from nova import loadables

class BaseAdapter(object):
    """Base class for adapter."""

    def is_trusted(self, host, trust):
        """Return True if the HostState isTrusted, otherwise False.
        Override this in a subclass.
        """
        raise NotImplementedError()


class AdapterHandler(loadables.BaseLoader):
    def __init__(self):
        super(AdapterHandler, self).__init__(BaseAdapter)


def all_filters():
    """Return a list of adapter classes found in this directory.

    This method is used as the default for available adapter
    and should return a list of all adapter classes available.
    """
    return AdapterHandler().get_all_classes()
