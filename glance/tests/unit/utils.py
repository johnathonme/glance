# Copyright 2012 OpenStack Foundation.
# All Rights Reserved.
#
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

from oslo.config import cfg

from glance.common import exception
from glance.common import wsgi
import glance.context
import glance.db.simple.api as simple_db
import glance.openstack.common.log as logging


CONF = cfg.CONF
LOG = logging.getLogger(__name__)

UUID1 = 'c80a1a6c-bd1f-41c5-90ee-81afedb1d58d'
UUID2 = '971ec09a-8067-4bc8-a91f-ae3557f1c4c7'

TENANT1 = '6838eb7b-6ded-434a-882c-b344c77fe8df'
TENANT2 = '2c014f32-55eb-467d-8fcb-4bd706012f81'

USER1 = '54492ba0-f4df-4e4e-be62-27f4d76b29cf'
USER2 = '0b3b3006-cb76-4517-ae32-51397e22c754'
USER3 = '2hss8dkl-d8jh-88yd-uhs9-879sdjsd8skd'

BASE_URI = 'swift+http://storeurl.com/container'


def get_fake_request(path='', method='POST', is_admin=False, user=USER1,
                     tenant=TENANT1):
    req = wsgi.Request.blank(path)
    req.method = method

    kwargs = {
        'user': user,
        'tenant': tenant,
        'roles': [],
        'is_admin': is_admin,
    }

    req.context = glance.context.RequestContext(**kwargs)
    return req


class FakeDB(object):

    def __init__(self):
        self.reset()
        self.init_db()

    @staticmethod
    def init_db():
        images = [
            {'id': UUID1, 'owner': TENANT1, 'status': 'queued',
             'locations': [{'url': '%s/%s' % (BASE_URI, UUID1),
                            'metadata': {}}]},
            {'id': UUID2, 'owner': TENANT1, 'status': 'queued'},
        ]
        [simple_db.image_create(None, image) for image in images]

        members = [
            {'image_id': UUID1, 'member': TENANT1, 'can_share': True},
            {'image_id': UUID1, 'member': TENANT2, 'can_share': False},
        ]
        [simple_db.image_member_create(None, member) for member in members]

        simple_db.image_tag_set_all(None, UUID1, ['ping', 'pong'])

    @staticmethod
    def reset():
        simple_db.DATA = {
            'images': {},
            'members': [],
            'tags': {},
        }

    def __getattr__(self, key):
        return getattr(simple_db, key)


class FakeStoreAPI(object):
    def __init__(self, store_metadata=None):
        self.data = {
            '%s/%s' % (BASE_URI, UUID1): ('XXX', 3),
            '%s/fake_location' % (BASE_URI): ('YYY', 3)
        }
        self.acls = {}
        if store_metadata is None:
            self.store_metadata = {}
        else:
            self.store_metadata = store_metadata

    def create_stores(self):
        pass

    def set_acls(self, context, uri, public=False,
                 read_tenants=[], write_tenants=[]):
        self.acls[uri] = {
            'public': public,
            'read': read_tenants,
            'write': write_tenants,
        }

    def get_from_backend(self, context, location):
        try:
            scheme = location[:location.find('/') - 1]
            if scheme == 'unknown':
                raise exception.UnknownScheme(scheme=scheme)
            return self.data[location]
        except KeyError:
            raise exception.NotFound()

    def safe_delete_from_backend(self, uri, context, id, **kwargs):
        try:
            del self.data[uri]
        except KeyError:
            pass

    def schedule_delayed_delete_from_backend(self, uri, id, **kwargs):
        pass

    def delete_image_from_backend(self, context, store_api, image_id, uri):
        if CONF.delayed_delete:
            self.schedule_delayed_delete_from_backend(uri, image_id)
        else:
            self.safe_delete_from_backend(uri, context, image_id)

    def get_size_from_backend(self, context, location):
        return self.get_from_backend(context, location)[1]

    def add_to_backend(self, context, scheme, image_id, data, size):
        store_max_size = 7
        current_store_size = 2
        for location in self.data.keys():
            if image_id in location:
                raise exception.Duplicate()
        if not size:
            size = len(data.fd)
        if (current_store_size + size) > store_max_size:
            raise exception.StorageFull()
        if context.user == USER2:
            raise exception.Forbidden()
        if context.user == USER3:
            raise exception.StorageWriteDenied()
        self.data[image_id] = (data, size)
        checksum = 'Z'
        return (image_id, size, checksum, self.store_metadata)


class FakePolicyEnforcer(object):
    def __init__(self, *_args, **kwargs):
        self.rules = {}

    def enforce(self, _ctxt, action, target=None, **kwargs):
        """Raise Forbidden if a rule for given action is set to false."""
        if self.rules.get(action) is False:
            raise exception.Forbidden()

    def set_rules(self, rules):
        self.rules = rules


class FakeNotifier(object):
    def __init__(self, *_args, **kwargs):
        self.log = []

    def warn(self, event_type, payload):
        log = {}
        log['notification_type'] = "WARN"
        log['event_type'] = event_type
        log['payload'] = payload
        self.log.append(log)

    def info(self, event_type, payload):
        log = {}
        log['notification_type'] = "INFO"
        log['event_type'] = event_type
        log['payload'] = payload
        self.log.append(log)

    def error(self, event_type, payload):
        log = {}
        log['notification_type'] = "ERROR"
        log['event_type'] = event_type
        log['payload'] = payload
        self.log.append(log)

    def get_logs(self):
        return self.log
