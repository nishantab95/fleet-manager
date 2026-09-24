import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import 'data/api_client.dart';
import 'domain/role_models.dart';

typedef SignOut = Future<void> Function();

class SupervisorHomeScreen extends StatefulWidget {
  const SupervisorHomeScreen({
    required this.api,
    required this.onSignOut,
    super.key,
  });

  final ApiClient api;
  final SignOut onSignOut;

  @override
  State<SupervisorHomeScreen> createState() => _SupervisorHomeScreenState();
}

class _SupervisorHomeScreenState extends State<SupervisorHomeScreen> {
  List<SupervisorSite> _sites = const [];
  List<SupervisorEvent> _events = const [];
  bool _loading = true;
  bool _offline = false;
  String? _error;
  String? _message;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _load();
    _pollTimer = Timer.periodic(const Duration(seconds: 30), (_) => _load());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    if (mounted) setState(() => _loading = true);
    try {
      final sites = await widget.api.supervisorSites();
      final eventLists = await Future.wait(
        sites.map((site) => widget.api.supervisorEvents(site.id)),
      );
      if (!mounted) return;
      setState(() {
        _sites = sites;
        _events = eventLists.expand((items) => items).toList()
          ..sort((a, b) {
            if (a.isOpenEmergency != b.isOpenEmergency) {
              return a.isOpenEmergency ? -1 : 1;
            }
            return (b.deviceCreatedAt ?? DateTime(1970)).compareTo(
              a.deviceCreatedAt ?? DateTime(1970),
            );
          });
        _error = null;
        _offline = false;
      });
    } on ApiException catch (error) {
      if (error.isUnauthorized) {
        await widget.onSignOut();
        return;
      }
      if (!mounted) return;
      setState(() {
        _offline = error.isRetryable;
        _error = _friendlyError(error);
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _verify(SupervisorEvent event, String decision) async {
    String? reason;
    if (decision != 'APPROVED') reason = await _askReason(decision);
    if (decision != 'APPROVED' && reason == null) return;
    try {
      final updated = await widget.api.verifySupervisorEvent(
        event.id,
        decision: decision,
        reason: reason,
      );
      if (!mounted) return;
      setState(() {
        _events = _events
            .map((item) => item.id == updated.id ? updated : item)
            .toList();
        _message = decision == 'APPROVED'
            ? 'Record approved.'
            : 'Record marked $decision.';
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = _friendlyError(error));
    }
  }

  Future<String?> _askReason(String decision) async {
    final controller = TextEditingController();
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(
          decision == 'REJECTED' ? 'Reject record' : 'Dispute record',
        ),
        content: TextField(
          controller: controller,
          maxLines: 3,
          decoration: const InputDecoration(labelText: 'Reason'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('CANCEL'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('SUBMIT'),
          ),
        ],
      ),
    );
    controller.dispose();
    return result?.isEmpty == true ? null : result;
  }

  Future<void> _emergencyAction(SupervisorEvent event, String action) async {
    try {
      final updated = action == 'acknowledge'
          ? await widget.api.acknowledgeEmergency(event.id)
          : await widget.api.resolveEmergency(event.id);
      if (mounted) {
        setState(() {
          _events = _events
              .map((item) => item.id == updated.id ? updated : item)
              .toList();
          _message = action == 'acknowledge'
              ? 'Emergency acknowledged.'
              : 'Emergency resolved.';
        });
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = _friendlyError(error));
    }
  }

  Future<void> _call(String? phone) async {
    if (phone == null || phone.isEmpty) return;
    final uri = Uri(scheme: 'tel', path: phone);
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication) &&
        mounted) {
      setState(() => _error = 'Unable to open the phone dialer.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final openEmergencies = _events
        .where((item) => item.isOpenEmergency)
        .toList();
    final pending = _events
        .where((item) => item.isPending && !item.isEmergency)
        .length;
    return _RoleScaffold(
      title: 'Supervisor operations',
      subtitle: '${_sites.length} assigned site(s)',
      onRefresh: _load,
      onSignOut: widget.onSignOut,
      offline: _offline,
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          children: [
            if (_error != null) _ErrorBanner(message: _error!, onRetry: _load),
            if (_message != null) _MessageBanner(message: _message!),
            _SummaryStrip(
              items: [
                _SummaryValue(
                  'OPEN EMERGENCIES',
                  '${openEmergencies.length}',
                  Icons.warning_amber,
                  danger: openEmergencies.isNotEmpty,
                ),
                _SummaryValue(
                  'PENDING REVIEW',
                  '$pending',
                  Icons.fact_check_outlined,
                ),
                _SummaryValue(
                  'SITES',
                  '${_sites.length}',
                  Icons.location_on_outlined,
                ),
              ],
            ),
            const SizedBox(height: 18),
            Text('EMERGENCIES', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            if (_loading && _events.isEmpty)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(28),
                  child: CircularProgressIndicator(),
                ),
              )
            else if (openEmergencies.isEmpty)
              const _EmptyCard(
                icon: Icons.check_circle_outline,
                text: 'No open emergencies.',
              )
            else
              for (final event in openEmergencies)
                _EmergencyCard(
                  event: event,
                  onCall: () => _call(event.driverPhone),
                  onAcknowledge: () => _emergencyAction(event, 'acknowledge'),
                  onResolve: () => _emergencyAction(event, 'resolve'),
                ),
            const SizedBox(height: 18),
            Text(
              'SITES / TIPPERS',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            for (final site in _sites)
              _SiteTippers(
                site: site,
                events: _events
                    .where((event) => event.siteId == site.id)
                    .toList(),
                onVerify: _verify,
                onCall: _call,
                onEvidence: _showEvidence,
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _showEvidence(SupervisorEvent event) async {
    if (!event.evidenceAvailable) return;
    showDialog<void>(
      context: context,
      builder: (context) => _EvidenceDialog(
        title: '${event.eventType} · ${event.tipperRegistration}',
        loader: () => widget.api.evidenceBytes(event.id, role: 'SUPERVISOR'),
      ),
    );
  }
}

class _SiteTippers extends StatelessWidget {
  const _SiteTippers({
    required this.site,
    required this.events,
    required this.onVerify,
    required this.onCall,
    required this.onEvidence,
  });

  final SupervisorSite site;
  final List<SupervisorEvent> events;
  final Future<void> Function(SupervisorEvent event, String decision) onVerify;
  final Future<void> Function(String? phone) onCall;
  final Future<void> Function(SupervisorEvent event) onEvidence;

  @override
  Widget build(BuildContext context) {
    final grouped = <String, List<SupervisorEvent>>{};
    for (final event in events) {
      grouped.putIfAbsent(event.tipperRegistration, () => []).add(event);
    }
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ExpansionTile(
        initiallyExpanded: grouped.isNotEmpty,
        title: Text(
          site.name,
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        subtitle: Text(
          '${grouped.length} tipper(s) · ${events.where((e) => e.isPending).length} pending',
        ),
        children: [
          if (grouped.isEmpty)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('No operational events for this site.'),
            ),
          for (final entry in grouped.entries)
            _TipperGroup(
              registration: entry.key,
              events: entry.value,
              onVerify: onVerify,
              onCall: onCall,
              onEvidence: onEvidence,
            ),
        ],
      ),
    );
  }
}

class _TipperGroup extends StatelessWidget {
  const _TipperGroup({
    required this.registration,
    required this.events,
    required this.onVerify,
    required this.onCall,
    required this.onEvidence,
  });

  final String registration;
  final List<SupervisorEvent> events;
  final Future<void> Function(SupervisorEvent event, String decision) onVerify;
  final Future<void> Function(String? phone) onCall;
  final Future<void> Function(SupervisorEvent event) onEvidence;

  @override
  Widget build(BuildContext context) {
    final trips = events.where((e) => e.isTrip).toList();
    final km = events.where((e) => e.isKm).toList();
    final diesel = events.where((e) => e.isDiesel).toList();
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 0, 12, 12),
      decoration: BoxDecoration(
        color: Theme.of(
          context,
        ).colorScheme.surfaceContainerHighest.withValues(alpha: .35),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Material(
        type: MaterialType.transparency,
        borderRadius: BorderRadius.circular(12),
        child: ExpansionTile(
          title: Text(registration),
          subtitle: Text('${events.where((e) => e.isPending).length} pending'),
          children: [
            _ReviewSection(
              title: 'TRIPS',
              events: trips,
              onVerify: onVerify,
              onCall: onCall,
              onEvidence: onEvidence,
            ),
            _ReviewSection(
              title: 'KM READINGS',
              events: km,
              onVerify: onVerify,
              onCall: onCall,
              onEvidence: onEvidence,
            ),
            _ReviewSection(
              title: 'DIESEL',
              events: diesel,
              onVerify: onVerify,
              onCall: onCall,
              onEvidence: onEvidence,
            ),
          ],
        ),
      ),
    );
  }
}

class _ReviewSection extends StatelessWidget {
  const _ReviewSection({
    required this.title,
    required this.events,
    required this.onVerify,
    required this.onCall,
    required this.onEvidence,
  });

  final String title;
  final List<SupervisorEvent> events;
  final Future<void> Function(SupervisorEvent event, String decision) onVerify;
  final Future<void> Function(String? phone) onCall;
  final Future<void> Function(SupervisorEvent event) onEvidence;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      title: Text(title, style: Theme.of(context).textTheme.labelLarge),
      initiallyExpanded: events.any((event) => event.isPending),
      children: [
        if (events.isEmpty)
          const Padding(padding: EdgeInsets.all(12), child: Text('No records')),
        for (final event in events)
          _ReviewEventCard(
            event: event,
            onVerify: onVerify,
            onCall: onCall,
            onEvidence: onEvidence,
          ),
      ],
    );
  }
}

class _ReviewEventCard extends StatelessWidget {
  const _ReviewEventCard({
    required this.event,
    required this.onVerify,
    required this.onCall,
    required this.onEvidence,
  });

  final SupervisorEvent event;
  final Future<void> Function(SupervisorEvent event, String decision) onVerify;
  final Future<void> Function(String? phone) onCall;
  final Future<void> Function(SupervisorEvent event) onEvidence;

  @override
  Widget build(BuildContext context) {
    final detail = event.isKm
        ? '${event.readingType == 'START_READING' ? 'START KM' : 'END KM'} · ${_numberText(event.readingValue)}'
        : event.isDiesel
        ? '${_numberText(event.litres)} LITRES'
        : event.isTrip
        ? 'Trip Complete'
        : '${event.emergencyCategory ?? 'Emergency'} · ${event.emergencyStatus ?? ''}';
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 0, 12, 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    detail,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                _StatusChip(event.verificationStatus),
              ],
            ),
            const SizedBox(height: 4),
            Text('${event.driverName} · ${_formatDate(event.deviceCreatedAt)}'),
            if (event.isDiesel && !event.evidenceAvailable)
              Text(
                'Evidence not provided',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: [
                if (event.evidenceAvailable)
                  TextButton.icon(
                    onPressed: () => onEvidence(event),
                    icon: const Icon(Icons.photo_outlined),
                    label: const Text('VIEW PHOTO'),
                  ),
                if (event.isEmergency && event.driverPhone != null)
                  TextButton.icon(
                    onPressed: () => onCall(event.driverPhone),
                    icon: const Icon(Icons.call_outlined),
                    label: const Text('CALL DRIVER'),
                  ),
                if (event.isPending && !event.isEmergency) ...[
                  TextButton(
                    onPressed: () => onVerify(event, 'APPROVED'),
                    child: const Text('APPROVE'),
                  ),
                  TextButton(
                    onPressed: () => onVerify(event, 'REJECTED'),
                    child: const Text('REJECT'),
                  ),
                  TextButton(
                    onPressed: () => onVerify(event, 'DISPUTED'),
                    child: const Text('DISPUTE'),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class OwnerHomeScreen extends StatefulWidget {
  const OwnerHomeScreen({
    required this.api,
    required this.onSignOut,
    super.key,
  });

  final ApiClient api;
  final SignOut onSignOut;

  @override
  State<OwnerHomeScreen> createState() => _OwnerHomeScreenState();
}

class _OwnerHomeScreenState extends State<OwnerHomeScreen> {
  OwnerDashboard? _dashboard;
  List<OwnerTipperReport> _tippers = const [];
  List<OwnerDutyReport> _duties = const [];
  List<SupervisorEvent> _alerts = const [];
  int _tab = 0;
  bool _loading = true;
  bool _offline = false;
  String? _error;
  DateTime _date = DateTime.now();
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _load();
    _pollTimer = Timer.periodic(const Duration(seconds: 60), (_) => _load());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    if (mounted) setState(() => _loading = true);
    try {
      final dashboard = await widget.api.ownerDashboard(date: _date);
      final siteReports = await Future.wait(
        dashboard.sites.map(
          (site) => widget.api.ownerSiteDaily(site.id, date: _date),
        ),
      );
      final tippers = siteReports.expand((items) => items).toList();
      final alerts =
          tippers
              .expand((item) => item.events)
              .where((event) => event.isEmergency || event.isPending)
              .toList()
            ..sort(
              (a, b) => (b.deviceCreatedAt ?? DateTime(1970)).compareTo(
                a.deviceCreatedAt ?? DateTime(1970),
              ),
            );
      final duties = await widget.api.ownerDuty(date: _date);
      if (!mounted) return;
      setState(() {
        _dashboard = dashboard;
        _tippers = tippers;
        _alerts = alerts;
        _duties = duties;
        _offline = false;
        _error = null;
      });
    } on ApiException catch (error) {
      if (error.isUnauthorized) {
        await widget.onSignOut();
        return;
      }
      if (mounted) {
        setState(() {
          _offline = error.isRetryable;
          _error = _friendlyError(error);
        });
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now().add(const Duration(days: 1)),
      initialDate: _date,
    );
    if (picked != null) {
      setState(() => _date = picked);
      await _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    final titles = ['Owner dashboard', 'Tippers', 'Sites', 'Alerts', 'Reports'];
    return _RoleScaffold(
      title: titles[_tab],
      subtitle: 'TODAY · ${_date.toIso8601String().substring(0, 10)}',
      onRefresh: _load,
      onSignOut: widget.onSignOut,
      offline: _offline,
      body: IndexedStack(
        index: _tab,
        children: [
          _OwnerDashboardBody(
            dashboard: _dashboard,
            duties: _duties,
            loading: _loading,
            error: _error,
            onRetry: _load,
          ),
          _OwnerTippersBody(tippers: _tippers, onEvidence: _showEvidence),
          _OwnerSitesBody(
            sites: _dashboard?.sites ?? const [],
            onPickDate: _pickDate,
          ),
          _OwnerAlertsBody(alerts: _alerts, onEvidence: _showEvidence),
          _OwnerReportsBody(
            date: _date,
            duties: _duties,
            onPickDate: _pickDate,
            onExport: _export,
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (value) => setState(() => _tab = value),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'HOME',
          ),
          NavigationDestination(
            icon: Icon(Icons.local_shipping_outlined),
            label: 'TIPPERS',
          ),
          NavigationDestination(
            icon: Icon(Icons.location_on_outlined),
            label: 'SITES',
          ),
          NavigationDestination(
            icon: Icon(Icons.warning_amber_outlined),
            label: 'ALERTS',
          ),
          NavigationDestination(
            icon: Icon(Icons.assessment_outlined),
            label: 'REPORTS',
          ),
        ],
      ),
    );
  }

  Future<void> _showEvidence(SupervisorEvent event) async {
    if (!event.evidenceAvailable) return;
    showDialog<void>(
      context: context,
      builder: (context) => _EvidenceDialog(
        title: '${event.eventType} · ${event.tipperRegistration}',
        loader: () => widget.api.evidenceBytes(event.id, role: 'OWNER_ADMIN'),
      ),
    );
  }

  Future<void> _export() async {
    try {
      final bytes = await widget.api.dailyExcel(date: _date);
      final directory = await getTemporaryDirectory();
      final path =
          '${directory.path}${Platform.pathSeparator}fleet-report-${_date.toIso8601String().substring(0, 10)}.xlsx';
      await File(path).writeAsBytes(bytes, flush: true);
      final file = XFile(
        path,
        mimeType:
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      );
      await Share.shareXFiles([file], text: 'Fleet Manager report');
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = _friendlyError(error));
    } on Object catch (error) {
      if (mounted) {
        setState(() => _error = 'Could not share the report: $error');
      }
    }
  }
}

class _OwnerDashboardBody extends StatelessWidget {
  const _OwnerDashboardBody({
    required this.dashboard,
    required this.duties,
    required this.loading,
    required this.error,
    required this.onRetry,
  });

  final OwnerDashboard? dashboard;
  final List<OwnerDutyReport> duties;
  final bool loading;
  final String? error;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    if (loading && dashboard == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (dashboard == null) {
      return _ErrorBanner(
        message: error ?? 'No report loaded.',
        onRetry: onRetry,
      );
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        if (error != null) _ErrorBanner(message: error!, onRetry: onRetry),
        Text('TODAY', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 10),
        _MetricGrid(
          metrics: [
            _Metric(
              'ACTIVE TIPPERS',
              '${dashboard!.activeTippers}',
              Icons.local_shipping_outlined,
            ),
            _Metric(
              'APPROVED TRIPS',
              '${dashboard!.approvedTrips}',
              Icons.check_circle_outline,
            ),
            _Metric(
              'DISTANCE',
              '${_numberText(dashboard!.distanceKm)} KM',
              Icons.route_outlined,
            ),
            _Metric(
              'DIESEL ISSUED',
              '${_numberText(dashboard!.dieselIssued)} L',
              Icons.local_gas_station_outlined,
            ),
          ],
        ),
        const SizedBox(height: 20),
        Text('ATTENTION', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 10),
        _MetricGrid(
          metrics: [
            _Metric(
              'PENDING',
              '${dashboard!.pending}',
              Icons.pending_actions_outlined,
              danger: dashboard!.pending > 0,
            ),
            _Metric(
              'MISSING KM',
              '${dashboard!.missingReadings}',
              Icons.speed_outlined,
              danger: dashboard!.missingReadings > 0,
            ),
            _Metric(
              'OPEN EMERGENCIES',
              '${dashboard!.openEmergencies}',
              Icons.warning_amber_outlined,
              danger: dashboard!.openEmergencies > 0,
            ),
            _Metric(
              'PAST REGULAR DUTY',
              '${dashboard!.driversPastDuty}',
              Icons.schedule_outlined,
              danger: dashboard!.driversPastDuty > 0,
            ),
          ],
        ),
        const SizedBox(height: 20),
        Text('DUTY MONITOR', style: Theme.of(context).textTheme.titleLarge),
        for (final duty in duties.take(5)) _DutyCard(duty: duty),
      ],
    );
  }
}

class _OwnerTippersBody extends StatelessWidget {
  const _OwnerTippersBody({required this.tippers, required this.onEvidence});

  final List<OwnerTipperReport> tippers;
  final Future<void> Function(SupervisorEvent) onEvidence;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
    children: [
      if (tippers.isEmpty)
        const _EmptyCard(
          icon: Icons.local_shipping_outlined,
          text: 'No tippers in this report day.',
        ),
      for (final tipper in tippers)
        Card(
          margin: const EdgeInsets.only(bottom: 12),
          child: ExpansionTile(
            title: Text(
              tipper.shortName ?? tipper.registration,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            subtitle: Text('${tipper.registration} · ${tipper.siteName}'),
            children: [
              ListTile(
                leading: const Icon(Icons.person_outline),
                title: const Text('Driver'),
                subtitle: Text(tipper.driverName),
              ),
              _KeyValueRow('Approved trips', '${tipper.approvedTrips}'),
              _KeyValueRow('Distance', '${_numberText(tipper.distanceKm)} KM'),
              _KeyValueRow('Diesel issued', '${_numberText(tipper.diesel)} L'),
              _KeyValueRow(
                'Completeness',
                tipper.missingStart || tipper.missingEnd
                    ? 'Missing KM'
                    : 'Complete',
              ),
              if (tipper.events.isNotEmpty)
                for (final event in tipper.events.take(8))
                  ListTile(
                    dense: true,
                    title: Text(event.eventType),
                    subtitle: Text(
                      '${_formatDate(event.deviceCreatedAt)} · ${event.verificationStatus}',
                    ),
                    trailing: event.evidenceAvailable
                        ? IconButton(
                            icon: const Icon(Icons.photo_outlined),
                            onPressed: () => onEvidence(event),
                          )
                        : null,
                  ),
            ],
          ),
        ),
    ],
  );
}

class _OwnerSitesBody extends StatelessWidget {
  const _OwnerSitesBody({required this.sites, required this.onPickDate});
  final List<OwnerSiteSummary> sites;
  final Future<void> Function() onPickDate;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
    children: [
      Align(
        alignment: Alignment.centerRight,
        child: OutlinedButton.icon(
          onPressed: onPickDate,
          icon: const Icon(Icons.calendar_today_outlined),
          label: const Text('REPORT DATE'),
        ),
      ),
      if (sites.isEmpty)
        const _EmptyCard(
          icon: Icons.location_on_outlined,
          text: 'No sites in this report day.',
        ),
      for (final site in sites)
        Card(
          child: ListTile(
            leading: const Icon(Icons.location_on_outlined),
            title: Text(site.name),
            subtitle: Text(
              '${site.tippers} tippers · ${site.approvedTrips} approved trips\n${_numberText(site.distanceKm)} KM · ${_numberText(site.diesel)} L diesel',
            ),
            isThreeLine: true,
            trailing: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text('${site.pending} pending'),
                Text(
                  '${site.emergencies} alerts',
                  style: TextStyle(
                    color: site.emergencies > 0
                        ? Theme.of(context).colorScheme.error
                        : null,
                  ),
                ),
              ],
            ),
          ),
        ),
    ],
  );
}

class _OwnerAlertsBody extends StatelessWidget {
  const _OwnerAlertsBody({required this.alerts, required this.onEvidence});
  final List<SupervisorEvent> alerts;
  final Future<void> Function(SupervisorEvent) onEvidence;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
    children: [
      if (alerts.isEmpty)
        const _EmptyCard(
          icon: Icons.check_circle_outline,
          text: 'No operational attention items.',
        ),
      for (final event in alerts)
        Card(
          color: event.isEmergency
              ? Theme.of(context).colorScheme.errorContainer
              : null,
          child: ListTile(
            leading: Icon(
              event.isEmergency ? Icons.warning_amber : Icons.pending_actions,
            ),
            title: Text(
              event.isEmergency
                  ? 'EMERGENCY · ${event.emergencyStatus ?? ''}'
                  : event.eventType,
            ),
            subtitle: Text(
              '${event.driverName} · ${event.tipperRegistration}\n${event.siteName} · ${_formatDate(event.deviceCreatedAt)}',
            ),
            isThreeLine: true,
            trailing: event.evidenceAvailable
                ? IconButton(
                    icon: const Icon(Icons.photo_outlined),
                    onPressed: () => onEvidence(event),
                  )
                : null,
          ),
        ),
    ],
  );
}

class _OwnerReportsBody extends StatelessWidget {
  const _OwnerReportsBody({
    required this.date,
    required this.duties,
    required this.onPickDate,
    required this.onExport,
  });
  final DateTime date;
  final List<OwnerDutyReport> duties;
  final Future<void> Function() onPickDate;
  final Future<void> Function() onExport;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
    children: [
      Row(
        children: [
          Expanded(
            child: Text(
              'Reports · ${date.toIso8601String().substring(0, 10)}',
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
          IconButton(
            onPressed: onPickDate,
            icon: const Icon(Icons.calendar_today_outlined),
          ),
        ],
      ),
      FilledButton.icon(
        onPressed: onExport,
        icon: const Icon(Icons.ios_share_outlined),
        label: const Text('DOWNLOAD / SHARE EXCEL'),
      ),
      const SizedBox(height: 20),
      Text(
        'DRIVER DUTY / OVERTIME',
        style: Theme.of(context).textTheme.titleLarge,
      ),
      const SizedBox(height: 8),
      if (duties.isEmpty)
        const _EmptyCard(
          icon: Icons.schedule_outlined,
          text: 'No duty sessions for this day.',
        ),
      for (final duty in duties) _DutyCard(duty: duty),
    ],
  );
}

class _DutyCard extends StatelessWidget {
  const _DutyCard({required this.duty});
  final OwnerDutyReport duty;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 10),
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  duty.driverName,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
              _StatusChip(duty.status),
            ],
          ),
          Text('${duty.tipperRegistration} · ${duty.siteName}'),
          const SizedBox(height: 8),
          _KeyValueRow('Duty start', _formatDate(duty.dutyStart)),
          _KeyValueRow('START KM', _numberText(duty.startKm)),
          _KeyValueRow('END KM', _numberText(duty.endKm)),
          _KeyValueRow('Regular duty end', _formatDate(duty.regularEnds)),
          _KeyValueRow('Actual duty end', _formatDate(duty.actualEnd)),
          _KeyValueRow(
            'Overtime',
            duty.status == 'ACTIVE'
                ? 'OT accruing / current ${duty.overtimeMinutes} min'
                : '${duty.overtimeMinutes} min',
          ),
        ],
      ),
    ),
  );
}

class _EvidenceDialog extends StatelessWidget {
  const _EvidenceDialog({required this.title, required this.loader});
  final String title;
  final Future<Uint8List> Function() loader;

  @override
  Widget build(BuildContext context) => Dialog(
    insetPadding: const EdgeInsets.all(12),
    child: FutureBuilder<Uint8List>(
      future: loader(),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const SizedBox(
            height: 360,
            child: Center(child: CircularProgressIndicator()),
          );
        }
        if (snapshot.hasError || snapshot.data == null) {
          return SizedBox(
            height: 240,
            child: Center(child: Text('Evidence could not be loaded.')),
          );
        }
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            AppBar(
              title: Text(title),
              automaticallyImplyLeading: false,
              actions: [
                IconButton(
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(Icons.close),
                ),
              ],
            ),
            Flexible(
              child: InteractiveViewer(
                child: Image.memory(snapshot.data!, fit: BoxFit.contain),
              ),
            ),
          ],
        );
      },
    ),
  );
}

class _RoleScaffold extends StatelessWidget {
  const _RoleScaffold({
    required this.title,
    required this.subtitle,
    required this.body,
    required this.onRefresh,
    required this.onSignOut,
    this.offline = false,
    this.bottomNavigationBar,
  });
  final String title;
  final String subtitle;
  final Widget body;
  final Future<void> Function() onRefresh;
  final SignOut onSignOut;
  final bool offline;
  final Widget? bottomNavigationBar;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontSize: 18)),
          Text(subtitle, style: Theme.of(context).textTheme.labelSmall),
        ],
      ),
      actions: [
        if (isPilotBuild)
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 4),
            child: Center(child: Text('PILOT')),
          ),
        IconButton(
          onPressed: onRefresh,
          tooltip: 'Refresh',
          icon: const Icon(Icons.refresh),
        ),
        IconButton(
          onPressed: onSignOut,
          tooltip: 'Sign out',
          icon: const Icon(Icons.logout),
        ),
      ],
    ),
    body: Column(
      children: [
        if (offline) const _OfflineBanner(),
        Expanded(child: body),
      ],
    ),
    bottomNavigationBar: bottomNavigationBar,
  );
}

class _SummaryStrip extends StatelessWidget {
  const _SummaryStrip({required this.items});
  final List<_SummaryValue> items;
  @override
  Widget build(BuildContext context) => Row(
    children: [
      for (final item in items)
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  children: [
                    Icon(
                      item.icon,
                      color: item.danger
                          ? Theme.of(context).colorScheme.error
                          : null,
                    ),
                    const SizedBox(height: 6),
                    Text(
                      item.value,
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    Text(
                      item.label,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
    ],
  );
}

class _SummaryValue {
  const _SummaryValue(this.label, this.value, this.icon, {this.danger = false});
  final String label;
  final String value;
  final IconData icon;
  final bool danger;
}

class _MetricGrid extends StatelessWidget {
  const _MetricGrid({required this.metrics});
  final List<_Metric> metrics;
  @override
  Widget build(BuildContext context) => GridView.count(
    crossAxisCount: 2,
    crossAxisSpacing: 10,
    mainAxisSpacing: 10,
    childAspectRatio: 1.55,
    shrinkWrap: true,
    physics: const NeverScrollableScrollPhysics(),
    children: [
      for (final metric in metrics)
        Card(
          color: metric.danger
              ? Theme.of(context).colorScheme.errorContainer
              : null,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(metric.icon),
                const SizedBox(height: 8),
                Text(
                  metric.value,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                Text(
                  metric.label,
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ],
            ),
          ),
        ),
    ],
  );
}

class _Metric {
  const _Metric(this.label, this.value, this.icon, {this.danger = false});
  final String label;
  final String value;
  final IconData icon;
  final bool danger;
}

class _EmergencyCard extends StatelessWidget {
  const _EmergencyCard({
    required this.event,
    required this.onCall,
    required this.onAcknowledge,
    required this.onResolve,
  });
  final SupervisorEvent event;
  final VoidCallback onCall;
  final VoidCallback onAcknowledge;
  final VoidCallback onResolve;
  @override
  Widget build(BuildContext context) => Card(
    color: Theme.of(context).colorScheme.errorContainer,
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'EMERGENCY',
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text('${event.driverName} · ${event.tipperRegistration}'),
          Text('${event.siteName} · ${_formatDate(event.deviceCreatedAt)}'),
          if (event.emergencyDescription != null)
            Text(event.emergencyDescription!),
          Wrap(
            spacing: 8,
            children: [
              if (event.driverPhone != null)
                TextButton.icon(
                  onPressed: onCall,
                  icon: const Icon(Icons.call_outlined),
                  label: const Text('CALL DRIVER'),
                ),
              if (event.emergencyStatus == 'OPEN')
                FilledButton(
                  onPressed: onAcknowledge,
                  child: const Text('ACKNOWLEDGE'),
                ),
              if (event.emergencyStatus == 'ACKNOWLEDGED')
                FilledButton(
                  onPressed: onResolve,
                  child: const Text('RESOLVE'),
                ),
            ],
          ),
        ],
      ),
    ),
  );
}

class _StatusChip extends StatelessWidget {
  const _StatusChip(this.status);
  final String status;
  @override
  Widget build(BuildContext context) => Chip(
    label: Text(status.replaceAll('_', ' ')),
    visualDensity: VisualDensity.compact,
  );
}

class _KeyValueRow extends StatelessWidget {
  const _KeyValueRow(this.label, this.value);
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 2),
    child: Row(
      children: [
        Expanded(child: Text(label)),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
      ],
    ),
  );
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message, required this.onRetry});
  final String message;
  final Future<void> Function() onRetry;
  @override
  Widget build(BuildContext context) => Card(
    color: Theme.of(context).colorScheme.errorContainer,
    child: ListTile(
      leading: const Icon(Icons.error_outline),
      title: Text(message),
      trailing: IconButton(onPressed: onRetry, icon: const Icon(Icons.refresh)),
    ),
  );
}

class _MessageBanner extends StatelessWidget {
  const _MessageBanner({required this.message});
  final String message;
  @override
  Widget build(BuildContext context) => Card(
    child: ListTile(
      leading: const Icon(Icons.check_circle_outline),
      title: Text(message),
    ),
  );
}

class _OfflineBanner extends StatelessWidget {
  const _OfflineBanner();
  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    color: Theme.of(context).colorScheme.tertiaryContainer,
    padding: const EdgeInsets.all(8),
    child: const Text(
      'OFFLINE · Showing the last available state',
      textAlign: TextAlign.center,
    ),
  );
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({required this.icon, required this.text});
  final IconData icon;
  final String text;
  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Row(
        children: [
          Icon(icon),
          const SizedBox(width: 12),
          Expanded(child: Text(text)),
        ],
      ),
    ),
  );
}

String _friendlyError(ApiException error) {
  if (error.statusCode == 401) {
    return 'Your session expired. Please sign in again.';
  }
  if (error.isRetryable) {
    return 'Fleet Manager server is unavailable. Check the Pilot server URL and connection.';
  }
  if (error.statusCode == 403) {
    return 'This account is not authorized for this role or data.';
  }
  return error.message.isEmpty
      ? 'Request could not be completed.'
      : error.message;
}

String _formatDate(DateTime? value) {
  if (value == null) return 'Time unavailable';
  return '${value.toLocal().day.toString().padLeft(2, '0')}/${value.toLocal().month.toString().padLeft(2, '0')} ${value.toLocal().hour.toString().padLeft(2, '0')}:${value.toLocal().minute.toString().padLeft(2, '0')}';
}

String _numberText(double? value) => value == null
    ? '—'
    : value.toStringAsFixed(value.truncateToDouble() == value ? 0 : 2);
