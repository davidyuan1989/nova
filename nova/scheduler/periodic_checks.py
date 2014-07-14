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

from nova import context
from nova import db
from nova.openstack.common import log as logging
from nova.openstack.common import periodic_task
from nova.openstack.common import timeutils
from nova.scheduler import adapters

class PeriodicChecks(object):
    '''This module contains 4 main functions:
        1. Accept user input through Nova API to create, update and
                delete checks
        2. Store checks and their parameters inside Ceilometer
                using (Ceilometer API?)
        3. Communicate with adapters for each running check
        4. Communicate with trusted_filer.py to provide it with a
                trusted compute pool periodically or when user asks
                for get_trusted_pool
    This component also mediates communication with OpenAttestation
    (OA) for the trusted_filter unless it is not running, in which case
    the trusted_filter will call OA directly.
    '''
        
    # list of running checks
    running_checks = {} 
    check_times = 0
    
    # periodic tasks not running by default
    periodic_tasks_running = False
    
    def __init__(self):
        ''' TODO:
            a. Get information about checks from Ceilometer
            b. Initialize adapters for each check
        '''
        admin = context.get_admin_context()
        self.compute_nodes = {}

        # set flag to show that periodic checks are now running
        PeriodicChecks.periodic_tasks_running = True
        # get all adapters
        self.adapter_handler = adapters.AdapterHandler()
        # all compute nodes
        self.compute_nodes = {}
        # all adapters in the adapters folder 
        self._get_all_adapters()
        # test code
        self.check_times = 1
        # start checks
        current_check_times = self.run_checks({})
        computes = db.compute_node_get_all(admin)
        for compute in computes:
            service = compute['service']
            host = service['host']
            self._init_cache_entry(host)
        
    def _init_cache_entry(self, host):
        self.compute_nodes[host] = {
            'trust_lvl': 'unknown',
            'vtime': timeutils.normalize_time(
                        timeutils.parse_isotime("1970-01-01T00:00:00Z"))}
     
    def _get_all_adapters(self):
        adapter_handler = adapters.AdapterHandler()
        classes = adapter_handler.get_matching_classes(
                ['nova.scheduler.adapters.all_adapters'])
        class_map = {}
        for cls in classes:
            class_map[cls.__name__] = cls
        return class_map
    
    @periodic_task.periodic_task(spacing=5,run_immediately=True)
    def run_checks(self, kwargs):
        ''' form a temporary compute pool to prevent unavailability of pool 
        during running checks'''
        if(PeriodicChecks.periodic_tasks_running):
            for host in self.compute_nodes:
                for adapter in adapters:
                    result = adapter.is_trusted(host, 'trusted')
                    current_host = self.compute_nodes[host]
                    current_host['trust_lvl'] = result
        self.check_times += 1
        return self.check_times
        
    
    ''' Add checks through horizon
    @param id: identifier for the check
    @param spacing: time between successive checks in seconds
    @param type-of_check: (optional) any additional info about of the check.
    '''
    def add_check(self, **kwargs):
        ''' check_id = kwargs['id']
        set the periodic tasks running flag to True
        TODO write new check into CONF and then call adapter
        '''
        PeriodicChecks.periodic_tasks_running = True
    
    def remove_check(self, **kwargs):
        ''' stop and delete adapter for this check and update Ceilometer 
        database
        '''        
        check_id = kwargs['id']
        if check_id not in self.running_checks:
            raise Exception("Check is not running")
        else:
            # stop the check
            self.running_checks[check_id] = None
            # remove it from list of running checks
            self.running_checks.pop(check_id)
            # check if there are no checks running
            if len(self.running_checks) == 0:
                PeriodicChecks.periodic_tasks_running = False
            
    def update_check(self, **kwargs):
        check_id = kwargs['id']
        new_spacing = kwargs['spacing']
        self.remove_check[check_id]
        ''' optional: also specify type_of_check'''
        self.add_check['id':check_id, 'spacing': new_spacing]

    ''' Used to check of periodic tasks are running by 
    scheduler.filters.trusted_filter
    '''
    def is_periodic_checks_running(self):
        if PeriodicChecks.periodic_tasks_running:
            return True;
        return False;

    def get_running_checks(self):
        return self.running_checks;

    def get_trusted_pool(self):
        if(PeriodicChecks.periodic_tasks_running):
            return self.compute_nodes
        return None

    def turn_off_periodic_check(self):
        PeriodicChecks.periodic_tasks_running = False

    def turn_on_periodic_check(self):
        PeriodicChecks.periodic_tasks_running = True