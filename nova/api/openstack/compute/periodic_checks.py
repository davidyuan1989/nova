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

import base64
import os
import webob.exc

from nova.api.openstack import common
from nova.api.openstack.compute.views import periodic_checks \
    as views_periodic_checks
from nova.api.openstack import wsgi
from nova.api.openstack import xmlutil
from nova import db
from nova import exception
from nova.openstack.common import gettextutils
from nova.scheduler import periodic_checks
from nova.scheduler import rpcapi


_ = gettextutils._


SUPPORTED_FILTERS = {
    'name': 'name',
    'desc': 'desc',
    'timeout': 'timeout',
    'spacing': 'spacing',
}


def make_periodic_check(elem):
    elem.set('id')
    elem.set('name')
    elem.set('desc')
    elem.set('timeout')
    elem.set('spacing')

    elem.append(common.MetadataTemplate())


periodic_check_nsmap = {None: xmlutil.XMLNS_V11, 'atom': xmlutil.XMLNS_ATOM}


class PeriodicCheckTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('periodic_check',
            selector='periodic_check')
        make_periodic_check(root)
        return xmlutil.MasterTemplate(root, 1, nsmap=periodic_check_nsmap)


class PeriodicChecksTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('periodic_checks')
        elem = xmlutil.SubTemplateElement(root, 'periodic_check',
            selector='periodic_check')
        make_periodic_check(elem)
        return xmlutil.MasterTemplate(root, 1, nsmap=periodic_check_nsmap)


class Controller(wsgi.Controller):
    """Base controller for retrieving/displaying periodic checks."""

    _view_builder_class = views_periodic_checks.ViewBuilder

    def __init__(self, **kwargs):
        """Initialize new `PeriodicCheckController`."""
        super(Controller, self).__init__(**kwargs)
        self.scheduler_rpcapi = rpcapi.SchedulerAPI()

    def _get_filters(self, req):
        """Return a dictionary of query param filters from the request.

        :param req: the Request object coming from the wsgi layer
        :retval a dict of key/value filters
        """
        filters = {}
        for param in req.params:
            if param in SUPPORTED_FILTERS or param.startswith('property-'):
                # map filter name or carry through if property-*
                filter_name = SUPPORTED_FILTERS.get(param, param)
                filters[filter_name] = req.params.get(param)

        # ensure server filter is the instance uuid
        filter_name = 'property-instance_uuid'
        try:
            filters[filter_name] = filters[filter_name].rsplit('/', 1)[1]
        except (AttributeError, IndexError, KeyError):
            pass

        filter_name = 'status'
        if filter_name in filters:
            # The API expects us to use lowercase strings for status
            filters[filter_name] = filters[filter_name].lower()

        return filters

    @wsgi.serializers(xml=PeriodicCheckTemplate)
    def show(self, req, id):
        """Return detailed information about a specific periodic check.

        :param req: `wsgi.Request` object
        :param name: Periodic check unique name
        """
        context = req.environ['nova.context']

        try:
            periodic_check = db.periodic_check_get_by_id(context, id)
        except (exception.NotFound):
            explanation = _("Periodic check not found.")
            raise webob.exc.HTTPNotFound(explanation=explanation)

        req.cache_db_items('periodic_checks', [periodic_check], 'id')
        return self._view_builder.show(req, periodic_check)

    def delete(self, req, id):
        """Delete a periodic check, if allowed.

        :param req: `wsgi.Request` object
        :param name: Periodic check unique name
        """
        context = req.environ['nova.context']
        try:
            periodic_check = db.periodic_check_get_by_id(context, id)
            db.periodic_check_delete_by_id(context, id)
            os.remove(("nova/scheduler/adapters/%s.py") % periodic_check.name)
            self.scheduler_rpcapi.del_periodic_check(context)
        except exception.NotFound:
            explanation = _("Periodic check not found.")
            raise webob.exc.HTTPNotFound(explanation=explanation)
        except exception.Forbidden:
            # This exception is raised on delete of OpenAttestation check
            explanation = \
                _("You are not allowed to delete the periodic check.")
            raise webob.exc.HTTPForbidden(explanation=explanation)
        return webob.exc.HTTPNoContent()

    @wsgi.serializers(xml=PeriodicCheckTemplate)
    def index(self, req):
        """Return an index listing of periodic checks available to the request.

        :param req: `wsgi.Request` object

        """
        context = req.environ['nova.context']
        #filters = self._get_filters(req)
        params = req.GET.copy()
        page_params = common.get_pagination_params(req)
        for key, val in page_params.iteritems():
            params[key] = val

        try:
            periodic_checks = db.periodic_check_get_all(context)
        except exception.Invalid as e:
            raise webob.exc.HTTPBadRequest(explanation=e.format_message())
        return self._view_builder.index(req, periodic_checks)

    @wsgi.serializers(xml=PeriodicChecksTemplate)
    def detail(self, req):
        """Return a detailed index listing of periodic checks.

        :param req: `wsgi.Request` object.

        """
        context = req.environ['nova.context']
        #filters = self._get_filters(req)
        params = req.GET.copy()
        page_params = common.get_pagination_params(req)
        for key, val in page_params.iteritems():
            params[key] = val
        try:
            periodic_checks = db.periodic_check_get_all(context)
        except exception.Invalid as e:
            raise webob.exc.HTTPBadRequest(explanation=e.format_message())

        req.cache_db_items('periodic_checks', periodic_checks, 'id')
        return self._view_builder.detail(req, periodic_checks)

    @wsgi.serializers(xml=PeriodicCheckTemplate)
    def create(self, req, body):
        """Create periodic check.

        :param req: `wsgi.Request` object
        :param body: Periodic check properties
        """
        context = req.environ['nova.context']

        try:
            periodic_check_dict = body['periodic_check']

            #id = periodic_check_dict['id']
            name = periodic_check_dict['name']
            #desc = periodic_check_dict['desc']
            #spacing = periodic_check_dict['spacing']
            #timeout = periodic_check_dict['timeout']

            code = base64.b64decode(periodic_check_dict['code'])
            check_file = open(("nova/scheduler/adapters/%s.py") % name,'w+')
            check_file.write(code)
            check_file.close()

            #periodic_checks.add_check(context, {id, name, desc, spacing, timeout})
            db.periodic_check_create(context, periodic_check_dict)
            periodic_check = db.periodic_check_get(context, name)
            self.scheduler_rpcapi.add_periodic_check(context)
        except exception.Invalid as e:
            raise webob.exc.HTTPBadRequest(explanation=e.format_message())

        return self._view_builder.show(req, periodic_check)
    
    @wsgi.serializers(xml=PeriodicCheckTemplate)
    def update(self, req, id, body):
        """Update periodic check.

        :param req: `wsgi.Request` object
        :param body: Periodic check properties
        """
        context = req.environ['nova.context']
 
        try:
            periodic_check_dict = body['periodic_check']

            name = periodic_check_dict['name']
            spacing = periodic_check_dict['spacing']
            db.periodic_check_update(context, name, periodic_check_dict)
            periodic_check = db.periodic_check_get(context, name)
            self.scheduler_rpcapi.update_periodic_check(context, name, spacing)
        except exception.Invalid as e:
            raise webob.exc.HTTPBadRequest(explanation=e.format_message())

        return self._view_builder.show(req, periodic_check)


def create_resource():
    return wsgi.Resource(Controller())
