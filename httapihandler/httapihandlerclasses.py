#
#    DjangoPBX
#
#    MIT License
#
#    Copyright (c) 2016 - 2023 Adrian Fretwell <adrian@djangopbx.com>
#
#    Permission is hereby granted, free of charge, to any person obtaining a copy
#    of this software and associated documentation files (the "Software"), to deal
#    in the Software without restriction, including without limitation the rights
#    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#    copies of the Software, and to permit persons to whom the Software is
#    furnished to do so, subject to the following conditions:
#
#    The above copyright notice and this permission notice shall be included in all
#    copies or substantial portions of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#    SOFTWARE.
#
#    Contributor(s):
#    Adrian Fretwell <adrian@djangopbx.com>
#

import os
from datetime import datetime
from django.core.cache import cache
from django.db.models import Q
from lxml import etree
from .httapihandler import HttApiHandler
from tenants.models import Domain
from tenants.pbxsettings import PbxSettings
from accounts.models import Extension, FollowMeDestination
from switch.models import IpRegister
from pbx.pbxsendsmtp import PbxTemplateMessage
from pbx.commonfunctions import shcommand
from ringgroups.ringgroupfunctions import RgFunctions
from accounts.extensionfunctions import ExtFunctions
from recordings.models import Recording
from callflows.models import CallFlows
from callflows.callflowfunctions import CfFunctions
from callflows.callflowevents import PresenceIn
from callblock.models import CallBlock
from conferencesettings.models import ConferenceCentres, ConferenceSessions


class TestHandler(HttApiHandler):

    handler_name = 'test'

    def get_data(self):
        if self.exiting:
            return self.return_data('Ok\n')

        x_root = self.XrootApi()
        etree.SubElement(x_root, 'params')
        x_work = etree.SubElement(x_root, 'work')
        etree.SubElement(x_work, 'execute', application='answer')
        x_log = etree.SubElement(x_work, 'log', level='NOTICE')
        x_log.text = 'Hello World'
        etree.SubElement(
            x_work,
            'playback',
            file='/usr/share/freeswitch/sounds/en/us/callie/ivr/8000/ivr-stay_on_line_call_answered_momentarily.wav'
            )
        etree.SubElement(x_work, 'hangup')

        etree.indent(x_root)
        xml = str(etree.tostring(x_root), "utf-8")
        return xml


class FollowMeToggleHandler(HttApiHandler):

    handler_name = 'followmetoggle'

    def get_variables(self):
        self.var_list = [
        'extension_uuid'
        ]
        self.var_list.extend(self.domain_var_list)

    def get_data(self):
        if self.exiting:
            return self.return_data('Ok\n')

        self.get_domain_variables()
        extension_uuid = self.qdict.get('extension_uuid')
        try:
            e = Extension.objects.get(pk=extension_uuid)
        except Extension.DoesNotExist:
            self.logger.debug(self.log_header.format('follow me toggle', 'Extn UUID not found'))
            return self.return_data(self.error_hangup('E1001'))

        x_root = self.XrootApi()
        etree.SubElement(x_root, 'params')
        x_work = etree.SubElement(x_root, 'work')
        etree.SubElement(x_work, 'execute', application='sleep', data='2000')
        if e.follow_me_enabled == 'true':
            etree.SubElement(
                x_work, 'playback',
                file='ivr/ivr-call_forwarding_has_been_cancelled.wav'
                )
            e.follow_me_enabled = 'false'
        else:
            etree.SubElement(
                x_work, 'playback',
                file='ivr/ivr-call_forwarding_has_been_set.wav'
                )
            e.follow_me_enabled = 'true'

        e.save()
        directory_cache_key = 'directory:%s@%s' % (e.extension, self.domain_name)
        cache.delete(directory_cache_key)
        etree.SubElement(x_work, 'hangup')
        etree.indent(x_root)
        xml = str(etree.tostring(x_root), "utf-8")
        return xml


class FollowMeHandler(HttApiHandler):

    handler_name = 'followme'

    def get_variables(self):
        self.var_list = [
        'call_direction',
        'extension_uuid'
        ]
        self.var_list.extend(self.domain_var_list)

    def get_data(self):
        if self.exiting:
            return self.return_data('Ok\n')

        self.get_domain_variables()
        call_direction = self.qdict.get('call_direction', 'local')
        extension_uuid = self.qdict.get('extension_uuid')
        if extension_uuid:
            extf = ExtFunctions(self.domain_uuid, self.domain_name, call_direction, extension_uuid)

        x_root = self.XrootApi()
        etree.SubElement(x_root, 'params')
        x_work = etree.SubElement(x_root, 'work')
        etree.SubElement(x_work, 'execute', application='set', data='hangup_after_bridge=true')
        etree.SubElement(x_work, 'execute', application='bridge', data=extf.generate_bridge())
        etree.indent(x_root)
        xml = str(etree.tostring(x_root), "utf-8")
        return xml


class FailureHandler(HttApiHandler):

    handler_name = 'failure'

    def get_variables(self):
        self.var_list = [
        'originate_disposition',
        'dialed_extension',
        'last_busy_dialed_extension',
        'forward_busy_enabled',
        'forward_busy_destination',
        'forward_busy_destination',
        'forward_no_answer_enabled',
        'forward_no_answer_destination',
        'forward_user_not_registered_enabled',
        'forward_user_not_registered_destination'
        ]
        self.var_list.extend(self.domain_var_list)

    def get_data(self):
        no_work = True
        if self.exiting:
            return self.return_data('Ok\n')

        self.get_domain_variables()
        originate_disposition = self.qdict.get('originate_disposition')
        dialed_extension = self.qdict.get('dialed_extension')
        context = self.qdict.get('Caller-Context')
        if not context:
            context = self.domain_name

        x_root = self.XrootApi()
        etree.SubElement(x_root, 'params')
        x_work = etree.SubElement(x_root, 'work')

        if originate_disposition == 'USER_BUSY':
            last_busy_dialed_extension = self.qdict.get('last_busy_dialed_extension', '~None~')
            if self.debug:
                self.logger.debug(self.log_header.format(
                    'falurehandler', 'last_busy_dialed_extension %s' % last_busy_dialed_extension
                    ))
            if dialed_extension and last_busy_dialed_extension:
                if not dialed_extension == last_busy_dialed_extension:
                    forward_busy_enabled = self.qdict.get('forward_busy_enabled', 'false')
                    if forward_busy_enabled:
                        if forward_busy_enabled == 'true':
                            forward_busy_destination = self.qdict.get('forward_busy_destination')
                            no_work = False
                            if forward_busy_destination:
                                etree.SubElement(
                                    x_work, 'execute', application='set',
                                    data='last_busy_dialed_extension=%s' % dialed_extension
                                    )
                                x_log = etree.SubElement(x_work, 'log', level='NOTICE')
                                x_log.text = 'forwarding on busy to: %s' % forward_busy_destination
                                etree.SubElement(
                                    x_work, 'execute', application='transfer',
                                    data='%s XML %s' % (forward_busy_destination, context)
                                    )
                            else:
                                x_log = etree.SubElement(x_work, 'log', level='NOTICE')
                                x_log.text = 'forwarding on busy with empty destination: hangup(USER_BUSY)'
                                etree.SubElement(x_work, 'hangup', cause='USER_BUSY')
            if no_work:
                etree.SubElement(x_work, 'hangup', cause='USER_BUSY')

        elif originate_disposition == 'NO_ANSWER':
            forward_no_answer_enabled = self.qdict.get('forward_no_answer_enabled')
            if forward_no_answer_enabled:
                if forward_no_answer_enabled == 'true':
                    forward_no_answer_destination = self.qdict.get('forward_no_answer_destination')
                    no_work = False
                    if forward_no_answer_destination:
                        x_log = etree.SubElement(x_work, 'log', level='NOTICE')
                        x_log.text = 'forwarding on no answer to: %s' % forward_no_answer_destination
                        etree.SubElement(
                            x_work, 'execute', application='transfer',
                            data='%s XML %s' % (forward_no_answer_destination, context)
                            )
                    else:
                        x_log = etree.SubElement(x_work, 'log', level='NOTICE')
                        x_log.text = 'forwarding on no answer with empty destination: hangup(NO_ANSWER)'
                        etree.SubElement(x_work, 'hangup', cause='NO_ANSWER')
            if no_work:
                etree.SubElement(x_work, 'hangup', cause='NO_ANSWER')

        elif originate_disposition == 'USER_NOT_REGISTERED':
            forward_user_not_registered_enabled = self.qdict.get('forward_user_not_registered_enabled')
            if forward_user_not_registered_enabled:
                if forward_user_not_registered_enabled == 'true':
                    forward_user_not_registered_destination = self.qdict.get(
                        'forward_user_not_registered_destination'
                        )
                    no_work = False
                    if forward_user_not_registered_destination:
                        x_log = etree.SubElement(x_work, 'log', level='NOTICE')
                        x_log.text = 'forwarding on not registerd to: %s' % forward_user_not_registered_destination
                        etree.SubElement(
                            x_work, 'execute', application='transfer',
                            data='%s XML %s' % (forward_user_not_registered_destination, context)
                            )
                    else:
                        x_log = etree.SubElement(x_work, 'log', level='NOTICE')
                        x_log.text = 'forwarding on user not registered with empty destination: hangup(NO_ANSWER)'
                        etree.SubElement(x_work, 'hangup', cause='NO_ANSWER')
            if no_work:
                etree.SubElement(x_work, 'hangup', cause='NO_ANSWER')

        elif originate_disposition == 'SUBSCRIBER_ABSENT':
            no_work = False
            x_log = etree.SubElement(x_work, 'log', level='NOTICE')
            x_log.text = 'subscriber absent: %s' % dialed_extension
            etree.SubElement(x_work, 'hangup', cause='UNALLOCATED_NUMBER')

        elif originate_disposition == 'CALL_REJECTED':
            no_work = False
            x_log = etree.SubElement(x_work, 'log', level='NOTICE')
            x_log.text = 'call rejected'
            etree.SubElement(x_work, 'hangup')

        if no_work:
            etree.SubElement(x_work, 'hangup')

        etree.indent(x_root)
        xml = str(etree.tostring(x_root), "utf-8")
        return xml


class HangupHandler(HttApiHandler):

    handler_name = 'hangup'

    def get_data(self):

        self.get_domain_variables()
        self.get_language_variables()

        missed_call_app  = self.qdict.get('missed_call_app')        # noqa: E221
        missed_call_data = self.qdict.get('missed_call_data')       # noqa: E221
        caller_id_name   = self.qdict.get('caller_id_name', ' ')    # noqa: E221
        caller_id_number = self.qdict.get('caller_id_number', ' ')  # noqa: E221
        sip_to_user      = self.qdict.get('sip_to_user', ' ')       # noqa: E221
        dialed_user      = self.qdict.get('dialed_user', ' ')       # noqa: E221

        if not missed_call_app:
            return self.return_data('Ok\n')
        if not missed_call_app == 'email':
            return self.return_data('Ok\n')
        if not missed_call_data:
            return self.return_data('Ok\n')

        m = PbxTemplateMessage()
        template = m.GetTemplate(
            self.domain_uuid, '%s-%s' % (self.default_language, self.default_dialect),
            'missed', 'default'
            )
        if not template[0]:
            self.logger.warn(self.log_header.format('hangup', 'Email Template mising'))
            return self.return_data('Ok\n')

        subject = template[0].format(
                caller_id_name=caller_id_name, caller_id_number=caller_id_number,
                sip_to_user=sip_to_user, dialed_user=dialed_user
                )
        body = template[1].format(
                caller_id_name=caller_id_name, caller_id_number=caller_id_number,
                sip_to_user=sip_to_user, dialed_user=dialed_user
                )
        out = m.Send(missed_call_data, subject, body, template[2])
        if self.debug or not out[0]:
            self.logger.warn(self.log_header.format('hangup', out[1]))

        return self.return_data('Ok\n')


class RegisterHandler(HttApiHandler):

    handler_name = 'register'

    def get_data(self):
        ip_address = self.qdict.get('network-ip', '192.168.42.1')
        status = self.qdict.get('status', 'N/A')
        if status.startswith('Registered'):
            ip, created = IpRegister.objects.update_or_create(address=ip_address)
            if created:
                if ':' in ip.address:
                    shcommand(["/usr/local/bin/fw-add-ipv6-sip-customer-list.sh", ip.address])
                else:
                    shcommand(["/usr/local/bin/fw-add-ipv4-sip-customer-list.sh", ip.address])

        return self.return_data('Ok\n')


class RingGroupHandler(HttApiHandler):

    handler_name = 'ringgroup'

    def get_variables(self):
        self.var_list = ['ring_group_uuid']
        self.var_list.extend(self.domain_var_list)

    def get_data(self):
        if self.exiting:
            return self.return_data('Ok\n')

        self.get_domain_variables()

        ringgroup_uuid = self.qdict.get('ring_group_uuid')
        try:
            rgf = RgFunctions(self.domain_uuid, self.domain_name, ringgroup_uuid)
        except:
            return self.return_data(self.error_hangup('R1001'))

        x_root = self.XrootApi()
        etree.SubElement(x_root, 'params')
        x_work = etree.SubElement(x_root, 'work')
        etree.SubElement(x_work, 'execute', application='bridge', data=rgf.generate_bridge())
        toa = rgf.generate_timeout_action()
        if toa[0] == 'hangup':
            etree.SubElement(x_work, toa[0])
        else:
            etree.SubElement(x_work, 'execute', application=toa[0], data=toa[1])

        etree.indent(x_root)
        xml = str(etree.tostring(x_root), "utf-8")
        return xml


class RecordingsHandler(HttApiHandler):

    handler_name = 'recordings'

    def get_variables(self):
        self.var_list = ['pin_number', 'recording_prefix']
        self.var_list.extend(self.domain_var_list)

    def get_data(self):
        self.get_domain_variables()
        if self.getfile:
            rec_file_exists = True
            # workaround since freeswitch 10 httapi record prepends a UUID to the filename
            # this strips it on the known part of the name 'recording'
            received_file_name = 'recording%s' % self.fdict['rd_input'].name.rsplit('recording', 1)[1]
            try:
                rec = Recording.objects.get(name=received_file_name)
            except Recording.DoesNotExist:
                rec_file_exists = False
                d = Domain.objects.get(pk=self.domain_uuid)
                rec = Recording.objects.create(name=received_file_name, domain_id=d, 
                        description='via recordings (%s)' % self.qdict.get('Caller-Destination-Number', ''))

            if rec_file_exists:
                rec.filename.delete(save=False)
            rec.filename.save(received_file_name, self.fdict['rd_input'])

        if self.exiting:
            return self.return_data('Ok\n')

        x_root = self.XrootApi()
        etree.SubElement(x_root, 'params')
        x_work = etree.SubElement(x_root, 'work')

        if 'next_action' in self.session.json[self.handler_name]:
            next_action =  self.session.json[self.handler_name]['next_action']
            if next_action == 'chk-pin':
                pin_number = self.session.json[self.handler_name]['pin_number']
                if pin_number == self.qdict.get('pb_input', ''):

                    self.session.json[self.handler_name]['next_action'] = 'record'
                    self.session.save()
                    x_work.append(self.play_and_get_digits('ivr/ivr-id_number.wav'))
                else:
                    etree.SubElement(x_work, 'playback', file='phrase:voicemail_fail_auth:#')
                    etree.SubElement(x_work, 'hangup')

            elif next_action == 'record':
                rec_no = self.qdict.get('pb_input', '')
                rec_prefix = self.qdict.get('recording_prefix', 'recording')
                self.get_sounds_variables()
                rec_file = '%s%s.wav' % (rec_prefix, rec_no)

                self.session.json[self.handler_name]['rec_file'] = '%s/%s/%s' % (self.recordings_dir, self.domain_name, rec_file)
                self.session.json[self.handler_name]['next_action'] = 'review'
                self.session.save()
                etree.SubElement(x_work, 'playback', file='ivr/ivr-recording_started.wav')
                x_work.append(self.record_and_get_digits(rec_file))

            elif next_action == 'review':
                rec_file = self.session.json[self.handler_name]['rec_file']
                self.session.json[self.handler_name]['next_action'] = 'rerecord'
                self.session.save()
                etree.SubElement(x_work, 'pause', milliseconds='1000')
                etree.SubElement(x_work, 'playback', file=rec_file)
                etree.SubElement(x_work, 'pause', milliseconds='500')
                etree.SubElement(x_work, 'playback', file='voicemail/vm-press.wav')
                etree.SubElement(x_work, 'playback', file='digits/1.wav')
                x_work.append(self.play_and_get_digits('voicemail/vm-rerecord.wav', 'pb_input', '~\\d{1}'))

            elif next_action == 'rerecord':
                re_rec = self.qdict.get('pb_input', '')
                if re_rec == '1':
                    rec_file = self.session.json[self.handler_name]['rec_file']
                    self.session.json[self.handler_name]['next_action'] = 'record'
                    self.session.save()
                    etree.SubElement(x_work, 'continue')
                else:
                    etree.SubElement(x_work, 'playback', file='ivr/ivr-recording_saved.wav')
                    etree.SubElement(x_work, 'hangup')
        else:
            pin_number = self.qdict.get('pin_number')
            if not pin_number:
                return self.error_hangup('R2001')

            self.session.json[self.handler_name]['pin_number'] = pin_number
            self.session.json[self.handler_name]['next_action'] = 'chk-pin'
            self.session.save()
            x_work.append(self.play_and_get_digits('phrase:voicemail_enter_pass:#'))

        etree.indent(x_root)
        xml = str(etree.tostring(x_root), "utf-8")
        return xml


class CallFlowToggleHandler(HttApiHandler):

    handler_name = 'callflowtoggle'

    def get_variables(self):
        self.var_list = [
        'callflow_uuid',
        'callflow_pin',
        ]
        self.var_list.extend(self.domain_var_list)

    def get_data(self):
        if self.exiting:
            return self.return_data('Ok\n')

        self.get_domain_variables()
        call_flow_uuid = self.qdict.get('callflow_uuid')
        try:
            q = CallFlows.objects.get(pk=call_flow_uuid)
        except CallFlows.DoesNotExist:
            self.logger.debug(self.log_header.format('call flow toggle', 'Call Flow UUID not found'))
            return self.return_data(self.error_hangup('D1001'))

        x_root = self.XrootApi()
        etree.SubElement(x_root, 'params')
        x_work = etree.SubElement(x_root, 'work')
        if 'next_action' in self.session.json[self.handler_name]:
            next_action =  self.session.json[self.handler_name]['next_action']
            if next_action == 'chk-pin':
                pin_number = self.session.json[self.handler_name]['pin_number']
                if pin_number == self.qdict.get('pb_input', ''):
                    etree.SubElement(x_work, 'pause', milliseconds='1000')
                    if q.status == 'true':
                        etree.SubElement(
                            x_work, 'playback',
                            file='ivr/ivr-night_mode.wav'
                            )
                        q.status = 'false'
                    else:
                        etree.SubElement(
                            x_work, 'playback',
                            file='ivr/ivr-day_mode.wav'
                            )
                        q.status = 'true'
                    q.save()
                    cff = CfFunctions(self.domain_uuid, self.domain_name, str(q.id))
                    cff.generate_xml()
                    etree.SubElement(x_work, 'pause', milliseconds='1000')
                    etree.SubElement(x_work, 'playback', file='voicemail/vm-goodbye.wav')
                    etree.SubElement(x_work, 'hangup')
                    directory_cache_key = 'dialplan:%s' % self.domain_name
                    cache.delete(directory_cache_key)
                    pe = PresenceIn(str(q.id), q.status, q.feature_code, self.domain_name)
                    pe.send()
                else:
                    etree.SubElement(x_work, 'playback', file='phrase:voicemail_fail_auth:#')
                    etree.SubElement(x_work, 'hangup')

        else:
            pin_number = self.qdict.get('callflow_pin')
            if not pin_number:
                return self.error_hangup('R2001')

            self.session.json[self.handler_name]['pin_number'] = pin_number
            self.session.json[self.handler_name]['next_action'] = 'chk-pin'
            self.session.save()
            x_work.append(self.play_and_get_digits('phrase:voicemail_enter_pass:#'))

        etree.indent(x_root)
        xml = str(etree.tostring(x_root), "utf-8")
        return xml

class CallBlockHandler(HttApiHandler):

    handler_name = 'callblock'

    def get_variables(self):
        self.var_list.extend(self.domain_var_list)

    def get_data(self):
        if self.exiting:
            return self.return_data('Ok\n')

        self.get_domain_variables()
        caller_id_name = self.qdict.get('Caller-Orig-Caller-ID-Name', 'None')
        caller_id_number = self.qdict.get('Caller-Orig-Caller-ID-Number', 'None')

        x_root = self.XrootApi()
        etree.SubElement(x_root, 'params')
        x_work = etree.SubElement(x_root, 'work')

        if not 'run' in self.session.json[self.handler_name]:
            self.session.json[self.handler_name]['run'] = False
            self.session.save()

            qs = CallBlock.objects.filter(
                ((Q(name=caller_id_name) | Q(name__isnull=True)) |
                (Q(number=caller_id_number) | Q(number__isnull=True)) |
                (Q(name=caller_id_name) & Q(number=caller_id_number))),
                domain_id=self.domain_uuid, enabled='true')
            if not qs:
                self.logger.debug(self.log_header.format('call block', 'No Call Block records found'))
            else:
                act = qs[0].data.split(':')
                etree.SubElement(x_work, 'execute', application=act[0], data=act[1])

        etree.SubElement(x_work, 'break')
        etree.indent(x_root)
        xml = str(etree.tostring(x_root), "utf-8")
        return xml


class ConferenceHandler(HttApiHandler):

    handler_name = 'conference'

    def get_variables(self):
        self.var_list = [
        'conference_uuid',
        ]
        self.var_list.extend(self.domain_var_list)

    def get_conf_session(self, profile='default', cnfroom=None):
        if 'sess_uuid' in self.session.json[self.handler_name]:
            try:
                self.conf_session = ConferenceSessions.objects.get(pk=self.session.json[self.handler_name]['sess_uuid'])
            except ConferenceSessions.DoesNotExist:
                self.conf_session = ConferenceSessions.objects.create(c_room_id=cnfroom, profile=profile)
        else:
            self.conf_session = ConferenceSessions.objects.create(c_room_id=cnfroom, profile=profile)
        return

    def get_live_session_count(self, c_room_id):
        return ConferenceSessions.objects.filter(c_room_id=c_room_id, live='true').count()

    def get_data(self):
        self.conf_session = None
        if self.getfile:
            received_file_name = 'conference-%s' % self.fdict['rd_input'].name
            with open('/tmp/%s' % received_file_name, "wb+") as destination:
                for chunk in self.fdict['rd_input'].chunks():
                    destination.write(chunk)
            self.session.json[self.handler_name]['name_recording'] = '/tmp/%s' % received_file_name
            self.session.save()

        if self.exiting:
            self.get_conf_session()
            if self.conf_session:
                self.conf_session.live = 'false'
                self.conf_session.save()
                if 'rec_tmp_flag_file' in self.session.json[self.handler_name]:
                    if self.get_live_session_count(self.conf_session.c_room_id) < 1:
                        try:
                            os.remove(self.session.json[self.handler_name]['rec_tmp_flag_file'])
                        except OSError:
                            pass
            if 'name_recording' in self.session.json[self.handler_name]:
                try:
                    os.remove(self.session.json[self.handler_name]['name_recording'])
                except OSError:
                    pass
            return self.return_data('Ok\n')

        self.get_domain_variables()
        caller_id_name = self.qdict.get('Caller-Orig-Caller-ID-Name', 'None')
        caller_id_number = self.qdict.get('Caller-Orig-Caller-ID-Number', 'None')

        if 'conf_uuid' not in self.session.json[self.handler_name]:
            conf_uuid = self.qdict.get('conference_uuid')
            try:
                cnf = ConferenceCentres.objects.get(pk=conf_uuid)
            except ConferenceCentres.DoesNotExist:
                self.logger.debug(self.log_header.format('conference', 'Conference UUID not found'))
                return self.return_data(self.error_hangup('C0001'))

        x_root = self.XrootApi()
        etree.SubElement(x_root, 'params')
        x_work = etree.SubElement(x_root, 'work')


        if 'next_action' in self.session.json[self.handler_name]:
            next_action =  self.session.json[self.handler_name]['next_action']
            if next_action == 'chk-pin':
                pin_number = self.qdict.get('pb_input')
                cnfroom = cnf.conferencerooms_set.filter(
                    (Q(participant_pin=pin_number) | Q(moderator_pin=pin_number)),
                    enabled='true').first()
                if cnfroom:
                    self.get_conf_session(cnfroom.c_profile_id.name, cnfroom)
                    flag_list = []
                    member_type = 1
                    if pin_number == cnfroom.participant_pin:
                        member_type = 0
                    if cnfroom.wait_mod == 'true' and member_type == 0:
                        flag_list.append('wait-mod')
                    if cnfroom.mute == 'true' and member_type == 0:
                        flag_list.append('mute')
                    if member_type == 1:
                        flag_list.append('moderator')

                    self.session.json[self.handler_name]['conf_uuid'] = str(cnfroom.id)
                    self.session.json[self.handler_name]['sess_uuid'] = str(self.conf_session.id)
                    self.session.json[self.handler_name]['name'] = cnfroom.name
                    self.session.json[self.handler_name]['profile'] = cnfroom.c_profile_id.name
                    self.session.json[self.handler_name]['max_members'] = str(cnfroom.max_members)
                    self.session.json[self.handler_name]['record'] = cnfroom.record
                    self.session.json[self.handler_name]['wait_mod'] = cnfroom.wait_mod
                    self.session.json[self.handler_name]['announce'] = cnfroom.announce
                    self.session.json[self.handler_name]['sounds'] = cnfroom.sounds
                    self.session.json[self.handler_name]['mute'] = cnfroom.mute
                    self.session.json[self.handler_name]['flags'] = '|'.join(flag_list)
                    self.session.json[self.handler_name]['member_type'] = member_type


                    if cnfroom.announce == 'true':
                        etree.SubElement(x_work, 'playback', file='ivr/ivr-say_name.wav')
                        x_work.append(self.record_and_get_digits('%s.wav' % self.session_id))

                    if cnfroom.record == 'true':
                        etree.SubElement(x_work, 'pause', milliseconds='500')
                        etree.SubElement(x_work, 'playback', file='ivr/ivr-recording_started.wav')

                    self.session.json[self.handler_name]['next_action'] = 'join-conf'
                    self.session.save()

                else:
                    self.session.json[self.handler_name].pop('next_action', None)
                    if 'pin_retries' in self.session.json[self.handler_name]:
                         self.session.json[self.handler_name]['pin_retries'] = self.session.json[self.handler_name]['pin_retries'] + 1 # noqa: E501
                    else:
                        self.session.json[self.handler_name]['pin_retries'] = 1
                    if self.session.json[self.handler_name]['pin_retries'] < 4:
                        etree.SubElement(x_work, 'playback', file='conference/conf-bad-pin.wav')
                    else:
                        etree.SubElement(x_work, 'playback', file='phrase:voicemail_fail_auth:#')
                        etree.SubElement(x_work, 'hangup')
                    self.session.save()
            elif next_action == 'join-conf':

                self.get_conf_session()

                if self.session.json[self.handler_name]['record'] == 'true':
                    rec_dir = PbxSettings().default_settings('switch', 'recordings', 'dir', '/var/lib/freeswitch/recordings', True)[0] # noqa: E501
                    dt = datetime.now()

                    rec_full_path = '%s/%s/archive/%s/%s/%s/%s.wav' % (rec_dir, self.domain_name, dt.strftime('%Y'), dt.strftime('%b'), dt.strftime('%d'), self.session.json[self.handler_name]['sess_uuid']) # noqa: E501
                    rec_tmp_flag_file = '/tmp/%s-recording' % self.session.json[self.handler_name]['conf_uuid']
                    try:
                        with open(rec_tmp_flag_file, "r") as rec_flag:
                            rec_full_path = rec_flag.read()
                    except FileNotFoundError:
                        with open(rec_tmp_flag_file, "w") as rec_flag:
                            rec_flag.write(rec_full_path)
                        record_data = 'res=${sched_api +6 none conference %s record %s}' % (self.session.json[self.handler_name]['conf_uuid'], rec_full_path) # noqa: E501
                        etree.SubElement(x_work, 'execute', application='set', data=record_data)

                    self.session.json[self.handler_name]['rec_tmp_flag_file'] = rec_tmp_flag_file
                    self.session.save()
                    self.conf_session.recording = rec_full_path
                    self.conf_session.caller_id_name = caller_id_name
                    self.conf_session.caller_id_number = caller_id_number
                    self.conf_session.save()

                if self.session.json[self.handler_name]['announce'] == 'true':
                    announce_data = 'res=${sched_api +1 none conference %s play file_string://%s!conference/conf-has_joined.wav}' % (self.session.json[self.handler_name]['conf_uuid'], self.session.json[self.handler_name]['name_recording']) # noqa: E501
                etree.SubElement(x_work, 'execute', application='set', data=announce_data)
                x_conference = etree.SubElement(x_work, 'conference', profile=self.session.json[self.handler_name]['profile'], flags=self.session.json[self.handler_name]['flags']) # noqa: E501
                x_conference.text = self.session.json[self.handler_name]['conf_uuid']

        else:
            self.session.json[self.handler_name]['next_action'] = 'chk-pin'
            self.session.save()
            x_work.append(self.play_and_get_digits('conference/conf-enter_conf_pin.wav'))


        etree.indent(x_root)
        xml = str(etree.tostring(x_root), "utf-8")
        return xml
