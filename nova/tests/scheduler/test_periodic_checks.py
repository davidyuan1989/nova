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
Tests For Periodic Check.
"""
import time

from nova import test
from nova.openstack.common import periodic_task
from nova.scheduler import periodic_checks as pc


class PeriodicTestCase(test.NoDBTestCase):
    """Test case for host adapters."""
    USES_DB = True
    periodic_cls =  pc.PeriodicChecks
    driver_cls_name = 'nova.scheduler.driver.Scheduler'
    periodic = periodic_cls()

    def setUp(self):
        super(PeriodicTestCase, self).setUp()
        self.flags(scheduler_driver=self.driver_cls_name)
        

    def test__init__(self):
        time.sleep(10)
        self.assertEqual(4,self.periodic.check_times)

    def test_periodic_task(self):
        #res = self.periodic.run_checks({})
    	self.assertEqual(3,self.periodic.check_times)
        
    def test_periodic_utils(self):
        @periodic_task.periodic_task(spacing=5,run_immediately=True)
        def run_sample_checks():
            return "100"
        self.assertEqual("100", run_sample_checks())
    	
    def test_compute_pool_init(self):
        compute_nodes = self.periodic.compute_nodes
        self.assertFalse(compute_nodes,None)

    def test_periodic_checks_off(self):
        ''' Test that when component is turned off, it returns None as the
        compute pool
        '''
        self.periodic.turn_off_periodic_check()
        self.assertEqual(None,self.periodic.get_trusted_pool())

    def test_periodic_checks_on(self):
        ''' Test that when component is turned on, it does not return None as the
        compute pool
        '''
        self.periodic.turn_off_periodic_check()
        self.periodic.turn_on_periodic_check()
        time.sleep(5)
        self.assertFalse(None,self.periodic.get_trusted_pool())