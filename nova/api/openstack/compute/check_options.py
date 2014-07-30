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

import webob.exc

from nova.api.openstack import common
from nova.api.openstack import wsgi
from nova.api.openstack import xmlutil
from nova import db
from nova import exception
from nova.openstack.common import gettextutils
from nova.scheduler import periodic_checks


_ = gettextutils._


def make_check_option(elem):
    elem.set('name')
    elem.set('value')

    elem.append(common.MetadataTemplate())


check_option_nsmap = {None: xmlutil.XMLNS_V11, 'atom': xmlutil.XMLNS_ATOM}


class CheckOptionsTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('check_options')
        elem = xmlutil.SubTemplateElement(root, 'check_option',
            selector='check_option')
        make_check_options(root)
        return xmlutil.MasterTemplate(root, 1, nsmap=check_option_nsmap)

class CheckOptionTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('check_options')
        make_check_options(root)
        return xmlutil.MasterTemplate(root, 1, nsmap=check_option_nsmap)


class Controller(wsgi.Controller):
    """Base controller for retrieving/displaying results."""

    def __init__(self, **kwargs):
        """Initialize new `ResultsController`."""
        super(Controller, self).__init__(**kwargs)

    @wsgi.serializers(xml=CheckOptionsTemplate)
    def index(self, req):
        """Return an index listing of results available to the request.

        :param req: `wsgi.Request` object

        """
        try:
            checks_enabled = \
                periodic_checks.PeriodicChecks().is_periodic_check_enabled()
            trusted_pool_saved = \
                periodic_checks.PeriodicChecks().is_trusted_pool_saved()
        except exception.Invalid as e:
            raise webob.exc.HTTPBadRequest(explanation=e.format_message())

        return {
            "check_options": [
                {
                    "name": "periodic_checks_enabled",
                    "value": checks_enabled
                },
                {
                    "name": "trusted_pool_saved",
                    "value": trusted_pool_saved
                }
            ]
        }

    @wsgi.serializers(xml=CheckOptionTemplate)
    def update():
        """Update periodic check options.

        :param req: `wsgi.Request` object
        :param body: properties
        """
        try:
            options_dict = body['check_option']

            name = options_dict['name']
            value = options_dict['value']
            if name == 'periodic_checks_enabled':
                periodic_checks.PeriodicChecks().set_periodic_check_enabled(value)
            if name == 'trusted_pool_saved':
                periodic_checks.PeriodicChecks().set_trusted_pool_saved(value)
        except exception.Invalid as e:
            raise webob.exc.HTTPBadRequest(explanation=e.format_message())


def create_resource():
    return wsgi.Resource(Controller())
