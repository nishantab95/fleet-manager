import 'dart:async';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import 'data/api_client.dart';
import 'data/secure_session_store.dart';
import 'data/sync_engine.dart';
import 'domain/driver_models.dart';

class DriverAppDependencies {
  const DriverAppDependencies({
    required this.api,
    required this.sessionStore,
    required this.sync,
    required this.installationIdentifier,
  });

  final ApiClient api;
  final SecureSessionStore sessionStore;
  final SyncEngine sync;
  final String installationIdentifier;
}

class FleetManagerApp extends StatelessWidget {
  const FleetManagerApp({super.key, this.dependencies});

  final DriverAppDependencies? dependencies;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Fleet Manager',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1B6B5A)),
        useMaterial3: true,
      ),
      home: dependencies == null
          ? const _UnavailableScreen()
          : DriverSessionScreen(dependencies: dependencies!),
    );
  }
}

class DriverSessionScreen extends StatefulWidget {
  const DriverSessionScreen({required this.dependencies, super.key});

  final DriverAppDependencies dependencies;

  @override
  State<DriverSessionScreen> createState() => _DriverSessionScreenState();
}

class _DriverSessionScreenState extends State<DriverSessionScreen> {
  DriverAssignment? _assignment;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_restoreSession());
  }

  Future<void> _restoreSession() async {
    final api = widget.dependencies.api;
    if (api.session == null) {
      if (mounted) setState(() => _loading = false);
      return;
    }
    try {
      await api.registerDevice(
        installationIdentifier: widget.dependencies.installationIdentifier,
      );
      final assignment = await api.currentAssignment();
      if (mounted) setState(() => _assignment = assignment);
    } on ApiException catch (error) {
      api.clearSession();
      await widget.dependencies.sessionStore.clear();
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _signedIn(DriverAssignment? assignment) {
    setState(() {
      _assignment = assignment;
      _error = null;
    });
  }

  Future<void> _signOut() async {
    try {
      await widget.dependencies.api.logout();
    } on ApiException {
      // Local credentials are cleared even when the device is offline.
      widget.dependencies.api.clearSession();
    }
    await widget.dependencies.sessionStore.clear();
    widget.dependencies.api.clearSession();
    if (mounted) setState(() => _assignment = null);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (widget.dependencies.api.session == null) {
      return LoginScreen(
        dependencies: widget.dependencies,
        initialError: _error,
        onSignedIn: _signedIn,
      );
    }
    return DriverHomeScreen(
      dependencies: widget.dependencies,
      assignment: _assignment,
      onSignOut: _signOut,
    );
  }
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    required this.dependencies,
    required this.onSignedIn,
    this.initialError,
    super.key,
  });

  final DriverAppDependencies dependencies;
  final ValueChanged<DriverAssignment?> onSignedIn;
  final String? initialError;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _phoneController = TextEditingController();
  final _otpController = TextEditingController();
  String? _challengeId;
  String? _preSessionToken;
  List<MembershipOption> _driverMemberships = const [];
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _error = widget.initialError;
  }

  @override
  void dispose() {
    _phoneController.dispose();
    _otpController.dispose();
    super.dispose();
  }

  Future<void> _requestOtp() async {
    await _run(() async {
      _challengeId = await widget.dependencies.api.requestOtp(
        _phoneController.text.trim(),
      );
    });
  }

  Future<void> _verifyOtp() async {
    final challengeId = _challengeId;
    if (challengeId == null) return;
    await _run(() async {
      _preSessionToken = await widget.dependencies.api.verifyOtp(
        challengeId: challengeId,
        otp: _otpController.text.trim(),
      );
      final memberships = await widget.dependencies.api.memberships(
        _preSessionToken!,
      );
      _driverMemberships = memberships
          .where((item) => item.role == 'DRIVER')
          .toList();
      if (_driverMemberships.length == 1) {
        await _selectMembership(_driverMemberships.single);
      }
      if (mounted) setState(() {});
    });
  }

  Future<void> _selectMembership(MembershipOption membership) async {
    final tokens = await widget.dependencies.api.createSession(
      preSessionToken: _preSessionToken!,
      membershipId: membership.membershipId,
    );
    await widget.dependencies.sessionStore.save(tokens);
    await widget.dependencies.api.registerDevice(
      installationIdentifier: widget.dependencies.installationIdentifier,
    );
    final assignment = await widget.dependencies.api.currentAssignment();
    widget.onSignedIn(assignment);
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final hasChallenge = _challengeId != null;
    final hasMembershipChoice = _driverMemberships.isNotEmpty;
    return Scaffold(
      appBar: AppBar(title: const Text('Driver sign in')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const Text(
            'Use your registered phone number to access today\'s assignment.',
            style: TextStyle(fontSize: 18),
          ),
          const SizedBox(height: 24),
          TextField(
            controller: _phoneController,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(labelText: 'Phone number'),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: _busy ? null : _requestOtp,
            child: const Text('REQUEST OTP'),
          ),
          if (hasChallenge) ...[
            const SizedBox(height: 20),
            TextField(
              controller: _otpController,
              keyboardType: TextInputType.number,
              maxLength: 6,
              decoration: const InputDecoration(labelText: 'One-time password'),
            ),
            FilledButton(
              onPressed: _busy ? null : _verifyOtp,
              child: const Text('VERIFY OTP'),
            ),
          ],
          if (hasMembershipChoice) ...[
            const SizedBox(height: 20),
            const Text('Choose your driver company'),
            for (final membership in _driverMemberships)
              ListTile(
                title: Text(membership.companyName),
                subtitle: Text(membership.role),
                onTap: _busy
                    ? null
                    : () => _run(() => _selectMembership(membership)),
              ),
          ],
          if (_error != null) ...[
            const SizedBox(height: 16),
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
        ],
      ),
    );
  }
}

class DriverHomeScreen extends StatefulWidget {
  const DriverHomeScreen({
    required this.dependencies,
    required this.assignment,
    required this.onSignOut,
    super.key,
  });

  final DriverAppDependencies dependencies;
  final DriverAssignment? assignment;
  final Future<void> Function() onSignOut;

  @override
  State<DriverHomeScreen> createState() => _DriverHomeScreenState();
}

class _DriverHomeScreenState extends State<DriverHomeScreen> {
  final _picker = ImagePicker();
  int _pendingCount = 0;
  String? _message;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    unawaited(_refreshQueue());
  }

  Future<void> _refreshQueue() async {
    final rows = await widget.dependencies.sync.database.pendingForSync();
    if (mounted) setState(() => _pendingCount = rows.length);
  }

  Future<void> _sync() async {
    setState(() => _busy = true);
    try {
      await widget.dependencies.sync.syncPending();
      await _refreshQueue();
      if (mounted) setState(() => _message = 'Sync complete');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _queue(
    DriverEventType eventType, {
    Map<String, dynamic> payload = const <String, dynamic>{},
    String? evidencePath,
  }) async {
    final assignment = widget.assignment;
    if (assignment == null) return;
    await widget.dependencies.sync.enqueue(
      assignment: assignment,
      eventType: eventType,
      payload: payload,
      evidencePath: evidencePath,
    );
    await _refreshQueue();
    if (mounted) {
      setState(
        () => _message = 'Saved on this device. It will sync when connected.',
      );
    }
  }

  Future<void> _showKmDialog() async {
    final result = await showDialog<_KmCapture>(
      context: context,
      builder: (context) => const _KmDialog(),
    );
    if (result == null) {
      return;
    }
    final photo = await _picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 85,
    );
    if (photo == null) {
      return;
    }
    await _queue(
      DriverEventType.kmReading,
      payload: {
        'reading_type': result.type.wireName,
        'reading_value': result.value,
      },
      evidencePath: photo.path,
    );
  }

  Future<void> _showDieselDialog() async {
    final litres = await showDialog<String>(
      context: context,
      builder: (context) => const _DieselDialog(),
    );
    if (litres == null) {
      return;
    }
    final photo = await _picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 85,
    );
    if (photo == null) {
      return;
    }
    await _queue(
      DriverEventType.diesel,
      payload: {'litres': litres},
      evidencePath: photo.path,
    );
  }

  Future<void> _showEmergencyDialog() async {
    final result = await showDialog<_EmergencyCapture>(
      context: context,
      builder: (context) => const _EmergencyDialog(),
    );
    if (result == null) {
      return;
    }
    await _queue(
      DriverEventType.emergency,
      payload: {
        'category': result.category.wireName,
        if (result.description.trim().isNotEmpty)
          'description': result.description.trim(),
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final assignment = widget.assignment;
    final canCapture = assignment != null;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Driver operations'),
        actions: [
          IconButton(
            tooltip: 'Sync',
            onPressed: _busy ? null : _sync,
            icon: const Icon(Icons.sync),
          ),
          IconButton(
            tooltip: 'Sign out',
            onPressed: widget.onSignOut,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          _AssignmentCard(assignment: assignment),
          const SizedBox(height: 20),
          Text(
            _pendingCount == 0
                ? 'All events synced'
                : '$_pendingCount event(s) waiting to sync',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 16),
          _ActionButton(
            label: 'TRIP COMPLETE',
            icon: Icons.check_circle_outline,
            onPressed: canCapture
                ? () => _queue(DriverEventType.tripComplete)
                : null,
          ),
          _ActionButton(
            label: 'KM READING',
            icon: Icons.speed,
            onPressed: canCapture ? _showKmDialog : null,
          ),
          _ActionButton(
            label: 'DIESEL',
            icon: Icons.local_gas_station,
            onPressed: canCapture ? _showDieselDialog : null,
          ),
          _ActionButton(
            label: 'EMERGENCY',
            icon: Icons.warning_amber,
            danger: true,
            onPressed: canCapture ? _showEmergencyDialog : null,
          ),
          if (_message != null) ...[
            const SizedBox(height: 16),
            Text(_message!, textAlign: TextAlign.center),
          ],
        ],
      ),
    );
  }
}

class _AssignmentCard extends StatelessWidget {
  const _AssignmentCard({required this.assignment});

  final DriverAssignment? assignment;

  @override
  Widget build(BuildContext context) {
    if (assignment == null) {
      return Card(
        color: Theme.of(context).colorScheme.errorContainer,
        child: const Padding(
          padding: EdgeInsets.all(16),
          child: Text(
            'NO ACTIVE ASSIGNMENT\nEvents are disabled until a supervisor assigns a tipper and site.',
          ),
        ),
      );
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              assignment!.tipperShortName ??
                  assignment!.tipperRegistrationNumber,
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 4),
            Text(assignment!.tipperRegistrationNumber),
            Text('Site: ${assignment!.siteName}'),
            Text('Supervisor: ${assignment!.supervisorName}'),
          ],
        ),
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.label,
    required this.icon,
    required this.onPressed,
    this.danger = false,
  });

  final String label;
  final IconData icon;
  final VoidCallback? onPressed;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: SizedBox(
        height: 64,
        child: FilledButton.icon(
          onPressed: onPressed,
          style: danger
              ? FilledButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.error,
                )
              : null,
          icon: Icon(icon),
          label: Text(
            label,
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
        ),
      ),
    );
  }
}

class _KmCapture {
  const _KmCapture(this.type, this.value);

  final KmReadingType type;
  final String value;
}

class _KmDialog extends StatefulWidget {
  const _KmDialog();

  @override
  State<_KmDialog> createState() => _KmDialogState();
}

class _KmDialogState extends State<_KmDialog> {
  final _value = TextEditingController();
  KmReadingType _type = KmReadingType.startReading;

  @override
  void dispose() {
    _value.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('KM READING'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DropdownButtonFormField<KmReadingType>(
            initialValue: _type,
            items: const [
              DropdownMenuItem(
                value: KmReadingType.startReading,
                child: Text('Start reading'),
              ),
              DropdownMenuItem(
                value: KmReadingType.endReading,
                child: Text('End reading'),
              ),
            ],
            onChanged: (value) => setState(() => _type = value ?? _type),
          ),
          TextField(
            controller: _value,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Kilometres'),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('CANCEL'),
        ),
        FilledButton(
          onPressed: () {
            if (double.tryParse(_value.text.trim()) == null) return;
            Navigator.pop(context, _KmCapture(_type, _value.text.trim()));
          },
          child: const Text('CONTINUE'),
        ),
      ],
    );
  }
}

class _DieselDialog extends StatefulWidget {
  const _DieselDialog();

  @override
  State<_DieselDialog> createState() => _DieselDialogState();
}

class _DieselDialogState extends State<_DieselDialog> {
  final _litres = TextEditingController();

  @override
  void dispose() {
    _litres.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('DIESEL'),
      content: TextField(
        controller: _litres,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: const InputDecoration(labelText: 'Litres'),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('CANCEL'),
        ),
        FilledButton(
          onPressed: () {
            final value = double.tryParse(_litres.text.trim());
            if (value == null || value <= 0) return;
            Navigator.pop(context, _litres.text.trim());
          },
          child: const Text('CONTINUE'),
        ),
      ],
    );
  }
}

class _EmergencyCapture {
  const _EmergencyCapture(this.category, this.description);

  final EmergencyCategory category;
  final String description;
}

class _EmergencyDialog extends StatefulWidget {
  const _EmergencyDialog();

  @override
  State<_EmergencyDialog> createState() => _EmergencyDialogState();
}

class _EmergencyDialogState extends State<_EmergencyDialog> {
  EmergencyCategory _category = EmergencyCategory.breakdown;
  final _description = TextEditingController();

  @override
  void dispose() {
    _description.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('EMERGENCY'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DropdownButtonFormField<EmergencyCategory>(
            initialValue: _category,
            items: EmergencyCategory.values
                .map(
                  (value) =>
                      DropdownMenuItem(value: value, child: Text(value.label)),
                )
                .toList(),
            onChanged: (value) =>
                setState(() => _category = value ?? _category),
          ),
          TextField(
            controller: _description,
            maxLines: 3,
            maxLength: 500,
            decoration: const InputDecoration(
              labelText: 'Description (optional)',
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('CANCEL'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(
            context,
            _EmergencyCapture(_category, _description.text),
          ),
          child: const Text('SAVE EMERGENCY'),
        ),
      ],
    );
  }
}

class _UnavailableScreen extends StatelessWidget {
  const _UnavailableScreen();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: Text('Driver client dependencies are not initialized.'),
      ),
    );
  }
}
